# Getting Started

## Available solver

Atlas project uses or-tools as modeller, you can use the solver of your choice. We provided a special support for the commercial Xpress solver. Here is a quick install guide :

### Xpress for windows

- Download [file]('https://www.artelys.com/fr/espace-client/telecharger-xpress/') (You will probably need to create an account) and install the file
- Move your license  `xpauth.xpr` in `xpressmp/bin/`

### Xpress for linux

Find below a quick installation guide, more information can be find directly on **FICO** website : [here](https://www.fico.com/fico-xpress-optimization/docs/dms2021-02/installguide/dhtml/chapinst1_sec_secunix.html)

- Download [file]('https://www.artelys.com/fr/espace-client/telecharger-xpress/') (You will probably need to create an account)
- Move the archive here : `/opt/xpressmp`
- Enter the uncompressed archive : `cd <archive_uncompressed>`
- Run the installer, select **static licensing** :

```bash
sudo chmod +x install.sh
sudo ./install.sh
```

- Copy your license `xpauth.xpr` in `/opt/xpressmp/`

- In your `~/.bashrc` or `~/.zshrc` :

```bash
export XPRESS_DIR="/opt/xpressmp/y" # if the installer has created a subfolder y/
export XPAUTH_PATH="/opt/xpressmp/xpauth.xpr"
```

- Now make sure everything is working running in python:

```python
from atlas import OptimisationModel

model = OptimisationModel('xpress')
```
