# Running on Linux

Two options. The systemd user timer is better — it catches up on runs missed
while the laptop was suspended, which plain cron does not.

## Option A — systemd user timer (recommended)

Create `~/.config/systemd/user/vendorbot.service`:

```ini
[Unit]
Description=The Everyday Matcha — FB vendor call tracker

[Service]
Type=oneshot
WorkingDirectory=/home/YOUR_NAME/matcha-vendor-bot
ExecStart=/home/YOUR_NAME/matcha-vendor-bot/deploy/run-bot.sh
```

Create `~/.config/systemd/user/vendorbot.timer`:

```ini
[Unit]
Description=Run the vendor bot every 90 minutes

[Timer]
OnBootSec=5min
OnUnitActiveSec=90min
# Fire a missed run once the machine is back, instead of skipping it.
Persistent=true
# Spread the run over a 10 minute window so it isn't clockwork-regular.
RandomizedDelaySec=600

[Install]
WantedBy=timers.target
```

Enable it:

```bash
chmod +x ~/matcha-vendor-bot/deploy/run-bot.sh
systemctl --user daemon-reload
systemctl --user enable --now vendorbot.timer

# Let it keep running when you are not logged in
sudo loginctl enable-linger "$USER"
```

Check on it:

```bash
systemctl --user list-timers vendorbot.timer
journalctl --user -u vendorbot.service -n 50
tail -f ~/matcha-vendor-bot/data/bot.log
```

Stop it:

```bash
systemctl --user disable --now vendorbot.timer
```

## Option B — cron

```bash
chmod +x ~/matcha-vendor-bot/deploy/run-bot.sh
crontab -e
```

Add:

```cron
# Vendor bot — every 90 minutes between 8am and 11pm
0 8,11,14,17,20,23 * * * /home/YOUR_NAME/matcha-vendor-bot/deploy/run-bot.sh >> /home/YOUR_NAME/matcha-vendor-bot/data/cron.log 2>&1
```

Cron gets a minimal environment, so use absolute paths everywhere — that is
what the wrapper script is for.
