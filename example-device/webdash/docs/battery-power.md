# Battery & Power Management

## Hardware

- **PMU**: AXP228 (AllWinner/X-Powers)
- **Battery**: Li-Po (capacity reported via sysfs)
- **Charge controller**: Adjustable 300–900mA

## Charge Rate Control

```
charge.sh 300    # Gentle (300mA) — best for battery longevity
charge.sh 500    # Moderate (500mA)
charge.sh 900    # Maximum (900mA) — fastest charge
```

The charge rate is written to `/sys/class/power_supply/axp20x-battery/constant_charge_current`.

## Monitoring

```
battery.sh           # one-time snapshot
battery.sh watch     # live monitor (updates every 5s)
battery.sh log       # append entry to ~/battery.log
```

## Key Metrics

- **Capacity**: Reported % from fuel gauge
- **Voltage**: 3.0V (empty) to 4.2V (full)
- **Current**: Positive = charging, negative = discharging
- **Power**: Voltage x Current (mW)
- **Health**: Reported by PMU (Good/Overheat/Dead)

## Power Management

```
power.sh status      # screen brightness, battery, AC, uptime
power.sh reboot      # reboot (3s delay)
power.sh shutdown    # power off (3s delay)
```

## Tips

- Use 300mA charge rate when leaving plugged in overnight
- Monitor with `battery.sh watch` during heavy use to track drain rate
- The web dashboard shows real-time battery stats on the main page
