# System
import glob
import os
import tempfile
import shutil
import traceback
import uuid
import json
from dataclasses import dataclass
from json import JSONEncoder
from typing import List, Set, Dict, Optional, Any
import urllib.parse

import attr
import urllib
import urllib.request

from dataclasses_json import dataclass_json
# etc
from pathvalidate import sanitize_filename
from rich.progress import Progress

# TidalAPI
from tidalapi import Track, Album, Quality, Playlist

# Tidal DL NG
# Patching the config path
import tidal_dl_ng.config
from tidalapi.exceptions import ObjectNotFound


def my_path_config_base() -> str:
    return "config/tidal"
def my_path_file_token() -> str:
    return os.path.join(my_path_config_base(), "token.json")
def my_path_file_settings() -> str:
    return os.path.join(my_path_config_base(), "settings.json")

tidal_dl_ng.config.path_config_base = my_path_config_base
tidal_dl_ng.config.path_file_token = my_path_file_token
tidal_dl_ng.config.path_file_settings = my_path_file_settings
tidal_dl_ng.config.BaseConfig.path_base = my_path_config_base()

# Importing everything else in the tidal_dl_ng
from tidal_dl_ng.download import Download
from tidal_dl_ng.helper.decorator import SingletonMeta
from tidal_dl_ng.constants import SkipExisting, QualityVideo, CoverDimensions


class my_fn_logger:
    def error(*args):
        print(f"Error logged: {args}")

    def __call__(*args):
        print(f"Message logged: {args}")


@dataclass_json
@dataclass
class MyModelSettings:
    skip_existing: SkipExisting = SkipExisting.Disabled
    # TODO: Implement cover download to a separate file.
    # album_cover_save: bool = True
    lyrics_embed: bool = True
    lyrics_file: bool = False
    # TODO: Implement API KEY selection.
    # api_key_index: bool = 0
    # TODO: Implement album info download to separate file.
    # album_info_save: bool = False
    video_download: bool = True
    # TODO: Implement multi threading for downloads.
    # multi_thread: bool = False
    download_delay: bool = True
    download_base_path: str = "./dl"
    quality_audio: Quality = Quality.hi_res_lossless
    quality_video: QualityVideo = QualityVideo.P1080
    format_album: str = None
        #(
        #"Albums/{album_artist} - {album_title}{album_explicit}/{album_track_num}. {artist_name} - {track_title}"
    #))
    format_playlist: str = None #"Playlists/{playlist_name}/{artist_name} - {track_title}"
    format_mix: str = None #"Mix/{mix_name}/{artist_name} - {track_title}"
    format_track: str = None #"Tracks/{artist_name} - {track_title}{track_explicit}"
    format_video: str = None #"Videos/{artist_name} - {track_title}{track_explicit}"
    video_convert_mp4: bool = False
    path_binary_ffmpeg: str = None #""
    metadata_cover_dimension: CoverDimensions = CoverDimensions.Px1280
    extract_flac: bool = True
    downgrade_on_hi_res: bool = False

tidal_dl_ng.model.cfg.Settings = MyModelSettings

class MyBaseConfig:
    data: MyModelSettings
    file_path: str
    cls_model: MyModelSettings

    def set_option(self, key: str, value: Any) -> None:
        value_old: Any = getattr(self.data, key)

        if type(value_old) == bool:  # noqa: E721
            value = True if value.lower() in ("true", "1", "yes", "y") else False  # noqa: SIM210
        elif type(value_old) == int and type(value) != int:  # noqa: E721
            value = int(value)

        setattr(self.data, key, value)

    def read(self, path: str) -> bool:
        # Do nothing, no outer settings file
        self.data = self.cls_model
        return True

    def save(self, config_to_compare: str = None) -> None:
        # Do nothing, no outer settings file
        pass


original_BaseConfig_read = tidal_dl_ng.config.BaseConfig.read

def BaseConfig_read(self, path: str) -> bool:
    # Do nothing, no outer settings file
    if path.endswith("token.json"):
        return original_BaseConfig_read(self, path=path)
    else:
        self.data = self.cls_model
    return True
tidal_dl_ng.config.BaseConfig.read = BaseConfig_read

def BaseConfig_save(self, config_to_compare: str = None) -> None:
    # Do nothing, no outer settings file
    pass
tidal_dl_ng.config.BaseConfig.save = BaseConfig_save

#tidal_dl_ng.config.BaseConfig = MyBaseConfig
from tidal_dl_ng.config import BaseConfig

# class MySettings(BaseConfig, metaclass=SingletonMeta):
#     def __init__(self):
#         self.cls_model = MyModelSettings
#         #self.file_path = my_path_file_settings()
#         #self.read(self.file_path)
#         self.data = self.cls_model




# tidal_dl_ng.config.Settings = MySettings

from tidal_dl_ng.config import Settings, Tidal

settings = Settings()
tidal = Tidal(settings)
session = tidal.session
login_result = tidal.login(fn_print=print)
if not login_result:
    raise RuntimeError(f"Login to Tidal failed. Update the {my_path_file_token()} file")

#DL_FOLDER="./dl"

TRACKS_PART = 1000
def all_favorite_tracks() -> Dict[str, Track]:
    offset = 0
    result: Dict[str, Track] = {}
    while len(trs := tidal.session.user.favorites.tracks(limit=TRACKS_PART, offset=offset)) > 0:
        for tr in trs:
            result[tr.id] = tr
        offset += TRACKS_PART
    return result


ALBUMS_PART = 1000
def all_favorite_albums() -> Dict[str, Album]:
    offset = 0
    result: Dict[str, Album] = {}
    while len(trs := tidal.session.user.favorites.albums(limit=ALBUMS_PART, offset=offset)) > 0:
        for tr in trs:
            result[tr.id] = tr
        offset += ALBUMS_PART
    return result


PLAYLISTS_PART = 1000
def all_favorite_playlists() -> Dict[str, Playlist]:
    offset = 0
    result: Dict[str, Playlist] = {}
    while len(trs := tidal.session.user.favorites.playlists(limit=PLAYLISTS_PART, offset=offset)) > 0:
        for tr in trs:
            result[tr.id] = tr
        offset += PLAYLISTS_PART
    return result


# Collecting all the favorites
@attr.s
class FavoriteTrackJSON:
    author = attr.ib()
    album = attr.ib()
    filename = attr.ib()
    volume = attr.ib()


class DictJSONEncoder(JSONEncoder):
    def default(self, o):
        return attr.asdict(o)


class FavoriteTracksJSON:
    def __init__(self, library_dir):
        self.favorite_tracks: Dict[str, FavoriteTrackJSON] = {}

    def enlist(self, library_dir: str, id: str, track_json: FavoriteTrackJSON):
        self.favorite_tracks[id] = track_json

        with open(os.path.join(library_dir, "tidal_favorites.json"), "w") as favorites:
            json.dump(self.favorite_tracks, favorites, indent=4, cls=DictJSONEncoder)
        pass


class TidalCache:
    def __init__(self, library_dir: str):
        self.__dl = None
        self.__library_dir = library_dir

    def __download_track_if_not_present(self, album: Album, track: Track, temp_dir, line_prefix='  ') -> tuple[FavoriteTrackJSON, str]:
        file_template = os.path.join(temp_dir, f"tmpfile_{str(uuid.uuid4())}")
        if album.num_volumes > 1:
            rel_track_path = os.path.join(
                #self.__library_dir,
                sanitize_filename(track.artist.name),
                sanitize_filename(f"{album.year} - {track.album.name}"),
                sanitize_filename(f"Volume {track.volume_num}")
            )
        else:
            rel_track_path = os.path.join(
                #self.__library_dir,
                sanitize_filename(track.artist.name),
                sanitize_filename(f"{album.year} - {track.album.name}")
            )

        full_track_path = os.path.join(self.__library_dir, rel_track_path)
        rel_track_path_name_no_ext = os.path.join(rel_track_path, sanitize_filename(f"{track.track_num:02} {track.name}"))
        full_track_path_name_no_ext = os.path.join(self.__library_dir, rel_track_path_name_no_ext)
        rel_found_files = glob.glob(f"{glob.escape(rel_track_path_name_no_ext)}.*", root_dir=self.__library_dir)
        if len(rel_found_files) == 0:
            print(f"{line_prefix}Downloading: {track.artist.name} - {track.album.name} - {track.name}")

            result_dl, downloaded_tmp_path_file = self.__dl.item(
                media=track,
                file_template=file_template,
                download_delay=False,
                quality_audio=Quality.hi_res_lossless
            )

            tmpfileext = os.path.splitext(downloaded_tmp_path_file)[1]
            rel_track_path_name = f"{rel_track_path_name_no_ext}{tmpfileext}"
            full_track_path_name = f"{full_track_path_name_no_ext}{tmpfileext}"

            os.makedirs(full_track_path, exist_ok=True)
            shutil.move(downloaded_tmp_path_file, full_track_path_name, copy_function=shutil.copytree)

        else:
            print(f"{line_prefix}Already exists: {track.artist.name} - {track.album.name} - {track.name}")
            full_track_path_name = rel_found_files[0]
            rel_track_path_name = rel_found_files[0]

        return FavoriteTrackJSON(
            author=track.artist.name,
            album=track.album.name,
            filename=os.path.basename(full_track_path_name),
            volume=track.volume_num
        ), rel_track_path_name

    def update(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            print('* Caching all the albums marked "Favorite"... ', end='')
            my_fav_albums = all_favorite_albums()
            print(f"{len(my_fav_albums)} albums to check")

            favorite_tracks_json = FavoriteTracksJSON(self.__library_dir)

            self.__dl = Download(session=session,
                          path_base=temp_dir,
                          fn_logger=my_fn_logger, progress=Progress())

            for album in my_fav_albums.values():
                try:
                    for track in album.tracks():
                        fav_track_json, file_path = self.__download_track_if_not_present(album, track, temp_dir,
                                                                                         line_prefix='  ')
                        favorite_tracks_json.enlist(self.__library_dir, track.id, fav_track_json)
                except ObjectNotFound as e:
                    print(f"! Tracks object not found in the album \"{album.name}\" with id {album.id}. Maybe you don't need this album...")


            print('* Caching all the tracks marked "Favorite"... ', end='')
            my_fav_tracks = all_favorite_tracks()
            print(f"{len(my_fav_tracks)} tracks to check")

            cached_albums: Dict[str, Album] = {}
            for track in my_fav_tracks.values():
                if track.album.id not in my_fav_albums.keys():
                    # Downloading the album metadata for the track if needed
                    if track.album.id not in cached_albums:
                        album = tidal.session.album(track.album.id)
                        cached_albums[track.album.id] = album

                    fav_track_json, file_path = self.__download_track_if_not_present(cached_albums[track.album.id], track, temp_dir, line_prefix='  ')
                    favorite_tracks_json.enlist(self.__library_dir, track.id, fav_track_json)

            print("* Caching all the tracks from the user's playlists and user's favorites playlists")
            my_fav_playlists = all_favorite_playlists()
            for pl in tidal.session.user.playlists():
                my_fav_playlists[pl.id] = pl


            for playlist in my_fav_playlists.values():
                print(f"  - Playlist: {playlist.name}")

                with open(f"{os.path.join(self.__library_dir, sanitize_filename(playlist.name))}.m3u8", "w") as playlist_file:
                    playlist_file.write("#EXTM3U\n")
                    for track in playlist.tracks():
                        #№if track.album.id not in my_fav_albums.keys():
                        # Downloading the album metadata for the track if needed
                        if track.album.id not in cached_albums:
                            album = tidal.session.album(track.album.id)
                            cached_albums[track.album.id] = album

                        fav_track_json, file_path = self.__download_track_if_not_present(cached_albums[track.album.id], track,
                                                                                  temp_dir, line_prefix='    ')
                        #else:
                        #    pass
                        favorite_tracks_json.enlist(self.__library_dir, track.id, fav_track_json)

                        playlist_file.write(f"#EXTINF:{track.duration},{urllib.parse.quote(track.name)}\n{urllib.request.pathname2url(file_path)}")

        return favorite_tracks_json
