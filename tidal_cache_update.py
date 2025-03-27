import os
from tidal_cache import TidalCache

import attr
#import attrs
attr.SOME_FIELD=123


library_dir = "./tidal_cache"

if os.name == 'nt':
    from win32com.shell import shell, shellcon
    user_music_folder = shell.SHGetFolderPath(0, shellcon.CSIDL_MYMUSIC, None, 0)
    library_dir = os.path.join(user_music_folder, "TidalCache")


def main():
    cache = TidalCache(library_dir=library_dir)
    cache.update()


if __name__ == "__main__":
    main()
