## Configure LOCAL static ip for Raspiberry Pi 
This is needed to configure in foldersync app

Steps on ZTE Router
1. Goto 192.168.1.1
2. Select to LOCAL Network > LAN > DHCP Binding > Add Item
3. Configure the MAC address
  a. Get MAC address of rasphiberry pi by below command `ip link show`
  b. Configure IP address and MAC address with name
  c. So whenever raspberry pi boot next time it will get same ip adress configured


## Mount SSD
We need to permanently mount the SSD and point FolderSync to it using SFTP. So whenever rasphberry pi boots SSD get assigned same mount point

1. Identify SSD
    - Run `lsblk`, you should something like `sda` for ssd.

2. Identify SSD UUID
    - Run  `sudo blkid`, and using identify `sda` for hardrive, not uuid for SSD

3. Create Mount Point
    - Run `sudo mkdir -p /mnt/<custom-ssd-name>`. 
4. Automount the SSD on Boot
    - We need to configure File System Table (fstab) file
    - Run `sudo nano /etc/fstab`
    - Add line `UUID=YOUR-UUID-HERE /mnt/ssd_backup auto nosuid,nodev,nofail 0 0`
      - nofail ensures the Pi still boots if the SSD is unplugged)
    - Run Ctrl+O, Enter, Ctrl+X to save file.
4. Grant permission to ssd folder mounted 
    - `sudo chown -R yourusername:yourusername /mnt/ssd_backup`
5. Verification 
    - `sudo mount -a`
    - `df -h`

## Configure FolderSync
Add the SFTP Account
1. Go to Accounts > Add Account.
2. Select SFTP.
  - Server Address: Your Pi's Static IP.

  - Port: 22

  - Login: Your Pi username.

  - Password: Your Pi password.

- Tap Test Connection, then Save.

## Create the Sync Job (Folderpair)
1. Go to Folderpairs > Create Folderpair.
2. Set your Sync Type (e.g., "To right folder" to push backups from phone to Pi).
3. Left Account: Local Device (Select the folder on your Android device).
4. Right Account: Select your new Pi SFTP account.
5. Navigate to /mnt/ssd_backup to set the destination folder.
6. Configure Scheduling (e.g., daily) and Connection (e.g., specific Wi-Fi SSID) settings as