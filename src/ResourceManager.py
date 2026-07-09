import logging
import os
import sys

class ResourceManager:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(ResourceManager, cls).__new__(cls, *args, **kwargs)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            # Running as a bundled application; 'sys._MEIPASS' points to the _internal directory in PyInstaller's data tree
            self.base_dir = os.path.abspath(os.path.join(sys._MEIPASS, ".."))
        else:
            # Running as a raw script
            self.base_dir = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

        logging.info(f"Resource Manager initialized, base_dir is {self.base_dir}")

    def get_absolute_path(self, relative_path):
        path = os.path.join(self.base_dir, "resources", relative_path)
        if os.path.exists(path):
            return path
        else:
            logging.error(f"Resource Manager couldn't find {relative_path}")
            return None