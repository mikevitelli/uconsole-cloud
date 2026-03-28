# Bookworm Migration

## 1. Push from Bullseye (before shutdown)
```bash
cd ~ && git push
```

## 2. Shut down & swap SD card
```bash
sudo shutdown -h now
```
Wait for green LED to stop. Swap micro SD on CM4 carrier board.

## 3. First boot
- Set your username (e.g. `your-user`)
- Connect to wifi: `MyNetwork - 2.4GHz`

## 4. SSH in from other machine
```bash
ssh <username>@<uconsole-ip>
```

## 5. Install git & clone
```bash
sudo apt update && sudo apt install -y git
cd ~
git clone https://github.com/<your-github-user>/uconsole.git .
```

## 6. Run restore
```bash
chmod +x restore.sh
./restore.sh
```
Say **y** to each prompt. Packages will install one-by-one (slow but safe).

## 7. Restore SSH private keys
```bash
# from your other machine:
scp ~/.ssh/id_ed25519 <username>@<uconsole-ip>:~/.ssh/
# then on uconsole:
chmod 600 ~/.ssh/id_ed25519
```

## 8. Reboot
```bash
sudo reboot
```

## 9. Verify hardware
```bash
ls /dev/i2c-*        # I2C buses
ls /dev/spi*         # SPI devices
sudo hwclock -r      # RTC
iwconfig wlan0       # WiFi
```
