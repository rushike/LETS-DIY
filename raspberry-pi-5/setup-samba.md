Samba file server is easy way to share file over local network.

1. Update System
```bash
sudo apt update && sudo apt upgrade -y
```

2. Install Samba Software
```bash
sudo apt install samba samba-common-bin -y
```

3. Select Share directory
We can share an existing folder, create a new local directory, or map it to a mounted external NVMe SSD/HDD. 

4. Configure Samba Rules

    a. Backup existing samba config 
    ```bash
    sudo cp /etc/samba/smb.conf /etc/samba/smb.conf.backup
    ```
    b. Editing `smb.conf`
    ```bash
    sudo nano /etc/samba/smb.conf
    ```
      - Add below
        ```bash
        [PiShare]
        path = /home/<USERNAME>/shared
        writeable = yes
        browseable = yes
        public = no
        valid users = <USERNAME>
        ```
5. Create samba config
```bash
sudo smbpasswd -a <USERNAME>
```

6. Restart samba service
```bash
sudo systemctl restart smbd
```


7. Connect to drive\
  - **Windows**
    Navigate to `\\<YOUR_PI_IP_ADDRESS>\PiShare` using File Explorer \
  - **Mac**
   Open Finder, goto Go > Connect to server, `smb://<YOUR_PI_IP_ADDRESS>/PiShare`