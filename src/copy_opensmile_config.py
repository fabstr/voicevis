import opensmile
import shutil
import os

# Locate the config folder inside the installed opensmile package
src_config_dir = os.path.join(os.path.dirname(opensmile.__file__), 'core', 'config')
local_config_dir = './resources/smile_configs'

# Copy the entire config tree to your local project
if not os.path.exists(local_config_dir):
    shutil.copytree(src_config_dir, local_config_dir)
    print(f"Success: Configurations copied to {local_config_dir}")
else:
    print("Configuration directory already exists.")