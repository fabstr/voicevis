import logging
import os
import re
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

    def get_matching_files(self, regex_pattern, relative_dir=""):
        """
        Finds all files in the resources directory (or a specific relative_dir)
        that match the provided regex pattern.
        """
        search_dir = os.path.join(self.base_dir, "resources", relative_dir)
        matching_files = []

        if not os.path.exists(search_dir):
            logging.error(f"Resource Manager couldn't find the search directory: {search_dir}")
            return matching_files

        try:
            compiled_pattern = re.compile(regex_pattern)
        except re.error as e:
            logging.error(f"Invalid regex pattern '{regex_pattern}': {e}")
            return matching_files

        # Walk through the directory and its subdirectories
        for root, _, files in os.walk(search_dir):
            for file in files:
                if compiled_pattern.search(file):
                    matching_files.append(os.path.join(root, file))

        if not matching_files:
            logging.info(f"No files matched the regex '{regex_pattern}' in {search_dir}")

        return matching_files