# System
import glob
import os
import tempfile
import shutil
import uuid
import json
from json import JSONEncoder
from typing import List, Set, Dict, Optional

import attr
# etc
from pathvalidate import sanitize_filename
from rich.progress import Progress

# TidalAPI
from tidalapi import Track, Album, Quality

# Tidal DL NG
# Patching the config path
import tidal_dl_ng.config
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
from tidal_dl_ng.config import Settings, Tidal
from tidal_dl_ng.download import Download

def fn_logger_sample(*args):
    print(f"fn_logger_sample: {args}")
    pass

class MySettings(Settings):
    def __init__(self):
        super().__init__()
        self.file_path = "config/settings.json"
        self.read(self.file_path)

settings = Settings()
tidal = Tidal(settings)
session = tidal.session
result = tidal.login(fn_print=print)

TMP_FOLDER="./tmp"
DL_FOLDER="./dl"

TRACKS_PART = 1000
def all_favorite_tracks() -> Dict[int, Track]:
    offset = 0
    result: Dict[int, Track] = {}
    while len(trs := tidal.session.user.favorites.tracks(limit=TRACKS_PART, offset=offset)) > 0:
        for tr in trs:
            result[tr.id] = tr
        offset += TRACKS_PART
    return result


ALBUMS_PART = 1000
def all_favorite_albums() -> Dict[int, Album]:
    offset = 0
    result: Dict[int, Album] = {}
    while len(trs := tidal.session.user.favorites.albums(limit=ALBUMS_PART, offset=offset)) > 0:
        for tr in trs:
            result[tr.id] = tr
        offset += ALBUMS_PART
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


class TidalCache:
    def __init__(self):
        self.__dl = None

    def __download_track_if_not_present(self, album: Album, track: Track, temp_dir) -> FavoriteTrackJSON:
        file_template = os.path.join(temp_dir, f"tmpfile_{str(uuid.uuid4())}")

        if album.num_volumes > 1:
            track_path = os.path.join(
                DL_FOLDER,
                sanitize_filename(track.artist.name),
                sanitize_filename(f"{album.year} - {track.album.name}"),
                sanitize_filename(f"Volume {track.volume_num}")
            )
        else:
            track_path = os.path.join(
                DL_FOLDER,
                sanitize_filename(track.artist.name),
                sanitize_filename(f"{album.year} - {track.album.name}")
            )

        track_path_name_no_ext = os.path.join(track_path, sanitize_filename(f"{track.track_num:02} {track.name}"))
        found_files = glob.glob(f"{track_path_name_no_ext}.*")
        if len(found_files) == 0:
            print(f"Downloading: {track.artist.name} - {track.album.name} - {track.name}")

            result_dl, path_file = self.__dl.item(
                media=track,
                file_template=file_template,
                download_delay=False,
                quality_audio=Quality.hi_res_lossless
            )

            tmpfileext = os.path.splitext(path_file)[1]
            track_path_name = f"{track_path_name_no_ext}{tmpfileext}"

            os.makedirs(track_path, exist_ok=True)
            shutil.move(path_file, track_path_name)

        else:
            print(f"Already exists: {track.artist.name} - {track.album.name} - {track.name}")
            track_path_name = found_files[0]

        return FavoriteTrackJSON(
            author=track.artist.name,
            album=track.album.name,
            filename=os.path.basename(track_path_name),
            volume=track.volume_num
        )

    def update(self):
        my_favorite_albums = all_favorite_albums()

        favorite_tracks_json = {}

        with tempfile.TemporaryDirectory() as temp_dir:
            self.__dl = Download(session=session,
                          path_base=temp_dir,
                          fn_logger=fn_logger_sample, progress=Progress())

            for album in my_favorite_albums.values():
                for track in album.tracks():
                    fav_track_json = self.__download_track_if_not_present(album, track, temp_dir)
                    favorite_tracks_json[track.id] = fav_track_json

                    with open(os.path.join(DL_FOLDER, "tidal_favorites.json"), "w") as favorites:
                        json.dump(favorite_tracks_json, favorites, indent=4, cls=DictJSONEncoder)
                    pass

        return favorite_tracks_json
