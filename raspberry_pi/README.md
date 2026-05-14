# Installation Raspberry Pi

## Matériel nécessaire
- Raspberry Pi 3B+ ou 4
- Lecteur RFID RC522
- Webcam USB
- LED verte + LED rouge
- Résistances 330Ω

## Câblage RC522 → Raspberry Pi
| RC522 | Raspberry Pi |
|-------|-------------|
| SDA   | Pin 24 (GPIO8) |
| SCK   | Pin 23 (GPIO11) |
| MOSI  | Pin 19 (GPIO10) |
| MISO  | Pin 21 (GPIO9) |
| GND   | Pin 6 (GND) |
| RST   | Pin 22 (GPIO25) |
| 3.3V  | Pin 1 (3.3V) |

## Câblage LEDs
| LED     | Raspberry Pi |
|---------|-------------|
| Verte + | Pin 11 (GPIO17) |
| Rouge + | Pin 13 (GPIO27) |
| GND     | Pin 6 (GND) |

## Installation sur Raspberry Pi
```bash
pip install mfrc522 RPi.GPIO opencv-python requests deepface tf-keras torch
```

## Activer SPI sur Raspberry Pi
```bash
sudo raspi-config
# Interface Options → SPI → Enable
```

## Lancer
```bash
python pointage_pi.py
```