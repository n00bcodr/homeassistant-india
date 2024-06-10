[![My HA Version](https://img.shields.io/github/v/tag/n00bcodr/homeassistant-india?color=d42a1e&label=My%20HA%20Version&logo=homeassistant&logoColor=white&?cacheSeconds=600)](https://github.com/n00bcodr/homeassistant-india/blob/master/.HA_VERSION)
[![Latest HA Release](https://img.shields.io/github/v/release/home-assistant/home-assistant?include_prereleases&label=Latest%20HA%20Release&logo=home-assistant)](https://github.com/home-assistant/home-assistant/releases/latest)
[![Years Badge](https://badges.strrl.dev/years/n00bcodr?color=darkgreen)](https://github.com/n00bcodr)
![Commit Activity](https://img.shields.io/github/commit-activity/w/n00bcodr/homeassistant-india?color=f58153&?cacheSeconds=600)
[![Last Commit](https://img.shields.io/github/last-commit/n00bcodr/homeassistant-india?color=purple)](https://github.com/n00bcodr/homeassistant-india/commits/master)

---

[![Instagram](https://img.shields.io/badge/Instagram-%23E4405F.svg?style=for-the-badge&logo=Instagram&logoColor=white)](https://www.instagram.com/pavanthanuj/)
[![Facebook](https://img.shields.io/badge/Facebook-%231877F2.svg?style=for-the-badge&logo=Facebook&logoColor=white)](https://www.facebook.com/thanuj.upadrasta)
[![Reddit](https://img.shields.io/badge/Reddit-FF4500?style=for-the-badge&logo=reddit&logoColor=white)](https://www.reddit.com/user/pavanthanuj/)
[![Twitter](https://img.shields.io/badge/Twitter-%231DA1F2.svg?style=for-the-badge&logo=Twitter&logoColor=white)](https://www.twitter.com/pavanthanuj_u)
[![LinkedIn](https://img.shields.io/badge/linkedin-%230077B5.svg?style=for-the-badge&logo=linkedin&logoColor=white)](https://www.linkedin.com/in/pavanthanuju)
[![Spotify](https://img.shields.io/badge/Spotify-1ED760?style=for-the-badge&logo=spotify&logoColor=white)](https://open.spotify.com/user/21eb7srfkhj4oefepym2q5cpq)
[![Discord](https://img.shields.io/badge/Discord-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.com/users/beardbaba#3387)
---

# Home Assistant Configuraton

I started my Home Assistant Journey with a Raspberry Pi 3, from which I have switched to an old Dell Laptop that I had lying around, for a year. I recently migrated my setup to a renewed [HP Mini PC](https://www.amazon.in/gp/product/B09RTMLB15) with Core i7, 16GB RAM and a few hard disks connected with my Movie and TV Show collections.


## Things I use the server for

* [Home Assistant](https://home-assistant.io/)
* [Plex](https://www.plex.tv/) Media Server
* [dockerproxy](https://github.com/Tecnativa/docker-socket-proxy) to monitor various docker containers through Home Assistant
* [Broadlink Manager](https://hub.docker.com/r/techblog/broadlinkmanager) for reading IR codes
* [Watchtower](https://github.com/containrrr/watchtower) to have all the containers up-to date. This will cause the homeassistant instance to "unhealthy". Hence I am using a [workaround](https://gist.github.com/HCanber/700b4a5c685b9b97fb4865de6eaff0f3) for the same
* [Heimdall](https://hub.docker.com/r/linuxserver/heimdall) for browser start page
* [Transmission](https://transmissionbt.com/) installed as an app in Debian




## Devices I use
> ℹ️ I used Amazon Affiliate links below to help me buy more smart stuff 😄💰

## <a name="menu">Menu</a>
 | [Lights](#lights) | [Fans](#fans) | [Outlets & Switches](#outlets) | [Voice Assistants & Displays](#smartspeakers) | [Media](#media) | [Sensors](#sensors) | [Cameras](#cameras) | [Appliances](#appliances) | [Network](#network) | [IR Blasters](#ir) | [Climate](#climate) | [Other Hardware](#other) | [Screenshots](#screenshots) | [Graveyard☠️](#graveyard) |

---

### <a name="lights">Lights</a> 
| [Go to Menu](#menu) |
- [Wipro Smart Batons](https://amzn.to/3QuzgpS) x 1
- [Crompton Immensa Smart Batten](https://amzn.to/3HAG7dl) x 1
- [Wipro RGB Baton](https://amzn.to/3MZ1zcZ) x 1
- [Wipro 9W WW Bulbs](https://amzn.to/3xyKFMJ) x 6
- [Wipro 9W RGB Bulbs](https://amzn.to/3N3Es19) x 3
- [Philips Wiz 9W RGB Bulb](https://amzn.to/3O5V1KZ) x 1
- [WS2812B ARGB](https://cdn-shop.adafruit.com/datasheets/WS2812B.pdf) strip controlled by [ESP8266](https://www.espressif.com/en/products/socs/esp8266) running [WLED](https://github.com/Aircoookie/WLED) x 1
- [Protium WiFi RGBW Light Strip](https://amzn.to/3bbb1Ni) x 1
---

### <a name="fans">Fans</a> 
| [Go to Menu](#menu) |
- [Atomberg Renesa Smart+](https://amzn.to/3N4rPCG) x 1
- [Halonix Smart IOT ceiling fan kit](https://amzn.to/3tIxjMC) x 1
---

### <a name="outlets">Outlets & Switches</a> 
| [Go to Menu](#menu) |
- [Wipro 16A Smart Plugs](https://amzn.to/39uMfY7) x 2
- [Wipro 10A Smart Plugs](https://amzn.to/3xTLrnR) x 2
- [Sonoff POW R2](https://amzn.to/3xCmD3d) x 1
- [Sonoff Dual R2](https://amzn.to/3OmUK62) x 3
- [Sonoff Basic R2](https://amzn.to/3tGrDTo) x 4
- [Sonoff Mini R2](https://amzn.to/3aVsvwT) x 2


---
### <a name="smartspeakers">Voice Assistants & Displays</a> 
| [Go to Menu](#menu) |
- [Google Home Mini](https://www.flipkart.com/google-home-mini-assistant-smart-speaker/p/itm960a3af84a20b) x 3
- [Google Home](https://www.flipkart.com/google-home-assistant-smart-speaker/p/itm003b8619d4670) x 1
- [Google Nest Hub Max](https://store.google.com/us/product/google_nest_hub_max?hl=en-US) x 1
- [Amazon Echo Dot 3rd Gen](https://amzn.to/3QtkPCf) x 1
- [Amazon Echo Dot 2nd Gen](https://www.amazon.in/Amazon-RS03QR-Echo-Dot-Black/dp/B072DR5HYL) x 1
---
### <a name="media">Media</a> 
| [Go to Menu](#menu) |
- [Sony Bravia KD-65X85J](https://www.sony.co.in/electronics/televisions/x85j-series) x 1
- [OnePlus Y Series](https://amzn.to/3Hzm7aN) x 1
- [LG webOS TV 49UF690T](https://www.lg.com/in/support/product/lg-49UF690T.ATR) x 1

---
### <a name="sensors">Sensors</a> 
| [Go to Menu](#menu) |
- Temperature and Humidity Sensors from [Broadlink RM4 Mini](https://amzn.to/3N2an1P)


---
### <a name="cameras">Cameras</a> 
| [Go to Menu](#menu) |
- [HIKVISION DS-7A04HGHI-F1](https://amzn.to/3b7ZHRP) with 4 cameras
- [TP-LINK Tapo C200](https://amzn.to/39Ac0WS) x 1
- [TP-LINK Tapo C100](https://amzn.to/3N0Qecn) x 1

---
### <a name="appliances">Appliances</a> 
| [Go to Menu](#menu) |
- [Mi Air Purifier 3](https://amzn.to/3QnPfGl) x 1
- [LG Smart Refrigerator](https://www.lg.com/in/refrigerators/lg-GL-T432FPZ3)
- [Xbox One](https://en.wikipedia.org/wiki/Xbox_One) x 1
---
### <a name="network">Network</a> 
| [Go to Menu](#menu) |
- [TP-LINK Deco M5](https://amzn.to/3b4ETLa) x 3
- [TP-LINK Deco M3W](https://amzn.to/3xY0Iox) x 1
- [TP-Link AC1200 Archer A6](https://amzn.to/3Hwrs2F) x 1 (not being used)
---

### <a name="ir">IR Blasters</a> 
| [Go to Menu](#menu) |
- [Broadlink RM4 Mini](https://amzn.to/3N2an1P) with temperature and humidity sensor
- [Oakremote](https://amzn.to/3HwrKqh)
---

---
### <a name="climate">Climate</a> 
| [Go to Menu](#menu) |

No specific climate devices but two IR Blasters used to control ACs  using [Smart IR](https://github.com/smartHomeHub/SmartIR)

---
### <a name="other">Other Hardware</a> 
| [Go to Menu](#menu) |
- [Lenovo Tab M10 HD 2nd Gen](https://amzn.to/3QrldBm) - main dashboard |Screenshots|
- [Asus Nexus 7 Tablet](https://www.gsmarena.com/asus_google_nexus_7-4850.php) - Personal Dashboard
- [Canon imageCLASS MF244dw](https://in.canon/en/support/imageCLASS%20MF244dw/model)
- [HP Ink Tank Wireless 410 series](https://amzn.to/3mYtYFv)
---

### <a name="screenshots">Screenshots</a> 
| [Go to Menu](#menu) |

---

Personal Dashboard

![Personal Dashboard](https://github.com/n00bcodr/homeassistant-india/blob/master/Screenshots/PersonalDashboard.png?raw=true "Personal Dashboard")

---

Main Dashboard

![Main Dashboard 1](https://github.com/n00bcodr/homeassistant-india/blob/master/Screenshots/MainDashboard_1.jpeg?raw=true "Main Dashboard 1")
![Main Dashboard 2](https://github.com/n00bcodr/homeassistant-india/blob/master/Screenshots/MainDashboard_2.jpeg?raw=true "Main Dashboard 2")
![Main Dashboard 3](https://github.com/n00bcodr/homeassistant-india/blob/master/Screenshots/MainDashboard_3.jpeg?raw=true "Main Dashboard 3")
![Main Dashboard 4](https://github.com/n00bcodr/homeassistant-india/blob/master/Screenshots/MainDashboard_4.jpeg?raw=true "Main Dashboard 4")
---
Lovelace

![Lovelace 1](https://github.com/n00bcodr/homeassistant-india/blob/master/Screenshots/Lovelace_1.png?raw=true "Lovelace 1")
![Lovelace 2](https://github.com/n00bcodr/homeassistant-india/blob/master/Screenshots/Lovelace_2.png?raw=true "Lovelace 2")
![Lovelace 3](https://github.com/n00bcodr/homeassistant-india/blob/master/Screenshots/Lovelace_3.png?raw=true "Lovelace 3")
![Lovelace 4](https://github.com/n00bcodr/homeassistant-india/blob/master/Screenshots/Lovelace_4.png?raw=true "Lovelace 4")
![Lovelace 5](https://github.com/n00bcodr/homeassistant-india/blob/master/Screenshots/Lovelace_5.png?raw=true "Lovelace 5")
![Lovelace 6](https://github.com/n00bcodr/homeassistant-india/blob/master/Screenshots/Lovelace_6.png?raw=true "Lovelace 6")
![Lovelace 7](https://github.com/n00bcodr/homeassistant-india/blob/master/Screenshots/Lovelace_7.png?raw=true "Lovelace 7")
![Lovelace 8](https://github.com/n00bcodr/homeassistant-india/blob/master/Screenshots/Lovelace_8.png?raw=true "Lovelace 8")
![Lovelace 9](https://github.com/n00bcodr/homeassistant-india/blob/master/Screenshots/Lovelace_9.png?raw=true "Lovelace 9")

---

### <a name="graveyard">Graveyard☠️</a> 
| [Go to Menu](#menu) |

- [Wipro 10A Smart Plug](https://amzn.to/3xTLrnR) x 1
- [Sonoff Basic R2](https://amzn.to/3tGrDTo) x 6
- [Sonoff Mini R2](https://amzn.to/3aVsvwT) x 1
- [Sonoff Basic Zigbee R3](https://amzn.to/39BI9NO) x 1
- [Protium 16A Smart Wireless WIFI Switch](https://amzn.to/3tKHWP0) x 1
