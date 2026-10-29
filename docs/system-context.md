# Contexte système — ONEXPLAYER APEX sous SteamOS

Relevé du **2026-09-14** (uptime 10 h 30, session KDE Plasma / Wayland en mode
bureau, machine dockée). Remplace le relevé du 2026-08-26 ; les écarts sont
récapitulés au § 13.

Fiche de contexte matériel / firmware / pile logicielle pour tout travail sur ce
dépôt.

> **Note d'exécution** : les sessions Claude tournent dans le conteneur distrobox
> `claude` (Ubuntu 24.04). Tout ce relevé a été fait via `distrobox-host-exec`
> pour voir l'hôte SteamOS réel.

---

## 1. Machine

| | |
|---|---|
| Constructeur / modèle | ONE-NETBOOK **ONEXPLAYER APEX** (famille `ONEXPLAYER`, version `Standard`, SKU 1) |
| Carte mère | ONE-NETBOOK ONEXPLAYER APEX |
| BIOS / firmware | AMI **2.17**, daté du **2026-04-01** |
| EC firmware | **0.12** |
| Châssis DMI | type 37 ; systemd le classe `laptop` (le DMI ne déclare pas « handheld ») |

La détection par DMI (`sys_vendor` / `product_name`) reste fiable pour un quirk
device-specific.

## 2. SoC / CPU / GPU

| | |
|---|---|
| APU | **AMD Ryzen AI MAX+ 395 w/ Radeon 8060S** (« Strix Halo », famille 26, modèle 112) |
| Cœurs | 8 cœurs / 16 threads, 1 socket |
| Fréquences | 625 MHz → **5187 MHz** |
| Caches | L1d 384 Ko · L1i 256 Ko · L2 8 Mo · **L3 32 Mo** |
| Pilote P-state | `amd-pstate-epp`, gouverneur **powersave**, EPP `balance_performance` |
| iGPU | Radeon **8060S** — `amdgpu`, PCI `1002:1586`, DRM 3.65 |
| NPU | **XDNA** (`1022:17F0`), `amdxdna` chargé, `/dev/accel/accel0` |
| Mémoire unifiée | VRAM **16384 Mio** + GTT 15853 Mio |
| Mesa | radeonsi **26.1.2** (OpenGL 4.6) · `vulkan-radeon` 26.2.0-devel (build `26.05.16`) |

RAM système : **32 467 952 ko (~30,9 Gio)**, dont les 16 Gio de VRAM sont
ponctionnés (réglage BIOS, pas noyau).

Swap : **zram0 15,5 Gio (prio 100)** + `/home/swapfile` 1 Gio (prio -2).

## 3. Écrans — 3 actifs simultanément

Les trois sorties sont désormais allumées en même temps. **Les connecteurs DP ont
été renumérotés** par rapport au relevé précédent (`DP-9`/`DP-10` → `DP-5`/`DP-6`)
et le GPU n'expose plus que 8 connecteurs DP au lieu de 11 — conséquence directe
du changement de dock. **Ne jamais coder en dur un nom de connecteur DP.**

### Panneau interne — `eDP-1` (actif)

| | |
|---|---|
| Panneau | **BOE NS080WUM-LX1** (2024 S20), EDID 1.4 |
| Taille / résolution | **8,0"** (172 × 108 mm), **1920 × 1200** |
| Rafraîchissement | **120 Hz** natif |
| Rotation / échelle | monté en portrait → KDE applique `rotation 1` + `scale 1.2` (géométrie logique 1600 × 1000) |
| Position | 0,440 · priorité 3 |
| Luminosité | 31 % |
| VRR | `Always` · HDR/WCG : incapable |

### Externe 1 — SKG (**primaire**) — `DP-6` au dernier relevé

| | |
|---|---|
| Modèle | **SKG H32S17** (2025 S42) — **EDID passé en 1.4 / 384 octets** (était 1.3 / 256) |
| Diagonale déclarée | ⚠️ **EDID auto-contradictoire** — voir encadré ci-dessous |
| Mode actif | **2560 × 1440 @ 120 Hz** |
| **HDR** | **activé** — SDR 282 nits, crête 400 nits, **moyenne max 400 nits** (était 283) |
| WCG | activé · VRR : incapable |
| Position | 1600,0 · priorité 1 · scale 1 · luminosité 90 % |

> **Bug d'EDID sur le SKG H32S17 — c'est un 32", pas un 27".** Les deux champs
> de taille physique de son EDID se contredisent :
>
> | Champ | Valeur | Diagonale |
> |---|---|---|
> | Bloc de base (octets 21-22) | 70 × 39 cm | **31,5"** ← correct |
> | Descripteur de timing (DTD, octets 12-14) | 597 × 336 mm | 27,0" ← faux |
>
> `597 × 336 mm` est exactement la taille standard d'une dalle 27" 16:9 : le
> fabricant a recopié le DTD d'un autre modèle sans corriger les millimètres.
> X11, `xrandr` et le noyau privilégient le DTD (plus précis, en mm), d'où le
> « 27" » rapporté partout. Le voisin Acer EB321HQU, lui, est cohérent
> (70 × 39 cm et 699 × 393 mm donnent tous deux 31,5-31,6").
>
> Conséquence pratique : le DPI calculé est **109 au lieu de 93**, soit +17 %.
> Sans effet visible tant que l'échelle est forcée à 1, mais toute logique qui
> déduirait une échelle du DPI se tromperait sur cet écran.

### Externe 2 — Acer — `DP-5` au dernier relevé

| | |
|---|---|
| Modèle | **Acer EB321HQU** (2019 S12) — EDID 1.4 |
| Diagonale | 31,6" (699 × 393 mm) |
| Mode actif | **2560 × 1440 @ 59,91 Hz** |
| HDR / WCG / VRR | incapable |
| Position | 4160,0 · priorité 2 · scale 1 · luminosité 90 % · RgbRange `Automatic` |

**Bureau logique : 6720 × 1440** — eDP-1 à gauche (1600 × 1000 logiques), puis
SKG (1600,0), puis Acer (4160,0).

> **Les noms de connecteurs s'échangent d'un démarrage à l'autre.** Entre deux
> relevés à un jour d'intervalle, sans rien rebrancher, le SKG est passé de
> `DP-5` à `DP-6` et l'Acer de `DP-6` à `DP-5` — la géométrie et les priorités,
> elles, ont suivi les bons écrans. KDE s'en sort parce qu'il indexe sur un UUID
> dérivé de l'EDID, stable à travers les renumérotations :
>
> ```
> cc91b2c1-183e-4337-8983-8a51a02ddb4d  -> SKG H32S17   (DP-10 -> DP-5 -> DP-6)
> cbb8d055-f5e4-45ff-91eb-1b1ff6c292eb  -> Acer EB321HQU (DP-9  -> DP-6 -> DP-5)
> 802e2c0c-67de-46b6-9585-09da50f94b5d  -> BOE interne  (eDP-1, stable)
> ```
>
> **Identifier un écran par son EDID (nom/UUID), jamais par `DP-n`.**

> **Piège `xrandr`** : sous XWayland, `xrandr` rapporte les externes en
> `3072 × 1728` — c'est l'échelle globale 1,2 héritée de l'eDP appliquée au
> framebuffer X11. Le mode réel est `2560 × 1440` (confirmé par `kscreen-doctor`
> et `/sys/class/drm/*/modes`). **Se fier à kscreen-doctor / DRM, pas à xrandr.**

## 4. Dock — i-tec Thunderbolt 4 (nouveau)

Le dock VIA Labs USB-C a été remplacé par un **vrai dock Thunderbolt 4**.

| | |
|---|---|
| Modèle | **i-tec Thunderbolt 4 Dual DP Docking Station** — `TB4DUALDPDOCKPDPRO` |
| Vendeur | I-TEC Technologies S.R.O. (`3188:c141`) |
| Contrôleur | Intel **Goshen Ridge 2020** (`8086:0b26`) — 6 ponts PCIe tunnelés (bus 01/02) |
| Firmware NVM | **43.1** |
| Domaine | `0-2` sur **domain0** (routeur `c7:00.5`), `authorized: 1` |
| **Débit du lien** | **40 Gb/s symétriques** — `rx/tx_lanes = 2` × `rx/tx_speed = 20,0 Gb/s` |

> **Piège de lecture sysfs** : `rx_speed` / `tx_speed` sous
> `/sys/bus/thunderbolt/devices/` donnent la vitesse **par voie**, pas le débit
> agrégé. Lus seuls, ils affichent `20.0 Gb/s` et laissent croire à un lien
> dégradé. Il faut les multiplier par `rx_lanes` / `tx_lanes` (= 2 ici).
> `boltctl` fait le calcul et l'écrit noir sur blanc :
> `rx speed: 40 Gb/s = 2 lanes * 20 Gb/s`. **Se fier à `boltctl`, pas à
> `rx_speed` seul.** Ce noyau n'expose d'ailleurs plus `link_speed` /
> `link_width` (remplacés par les paires `*_speed` / `*_lanes`).
>
> Le lien est donc **conforme à la spec TB4**, sur le port USB-C 4 avec le câble
> d'origine. `domain1` (routeur `c7:00.6`) est vide, c'est normal : le dock est
> seul, branché sur `domain0`.

### Périphériques portés par le dock

| Composant | ID | Détail |
|---|---|---|
| Hub USB 3.0 Intel | `8087:0b40` | hub interne du Goshen Ridge, 10 Gbit/s |
| Hubs VIA Labs | `2109:0822`, `2109:0817`, `2109:2822`, `2109:2817` | cascade USB 3 / USB 2 |
| Hub Fresco Logic | `1d5c:5801` | racine USB 2 côté dock |
| **Ethernet** | **Realtek RTL8156** (`0bda:8156`) | **2,5 GbE** — lien négocié à **2500 Mb/s full duplex**, pilote `r8152` |
| Audio | Realtek **USB Audio** (`0bda:4ef0`) | jack combo du dock |
| Stockage USB | Générique (`21c4:b060`) | `usb-storage`, 5 Gbit/s |
| Billboards DP Alt | `2109:8822`, `2109:8817` | 2 négociations DP Alt Mode = les 2 sorties DP |

Profondeur de cascade : jusqu'à **4 niveaux de hub** (ex. Razer Ornata sur
`5-1.4.4.2`). Moins profond qu'avec l'ancien dock (5 niveaux), mais toujours un
facteur aggravant pour l'énumération USB.

## 5. Chaîne USB interne (celle qui pose problème)

Sur `usb1` / xHCI `c5:00.4` — **totalement distincte du dock**, inchangée :

```
usb1 (c5:00.4)
└── 1-1    1a86:8091  QinHeng USB HUB          <- hub interne
    ├── 1-1.1  1a2c:b001  ONE NETBOOK          <- HID boutons OXP
    ├── 1-1.2  1a86:fe00  HID                  <- clavier interne / touches Turbo
    └── 1-1.3  045e:028e  Xbox 360 pad         <- manette interne (xpad, js0)
```

`Microsoft X-Box 360 pad 0` (`js1`) est le périphérique virtuel produit par
Steam Input.

## 6. Autosuspend USB — état actuel

`usbcore.autosuspend = 2` (imposé par SteamOS). **`/etc/udev/rules.d/` est
toujours vide** : la règle persistante n'est pas installée.

```
1-1     (hub QinHeng)   control=auto   delay=0      <-- toujours pas protégé
1-1.1   ONE NETBOOK     control=on     delay=2000
1-1.2   HID interne     control=on     delay=2000
1-1.3   Xbox 360 pad    control=on     delay=2000
```

Situation identique au relevé précédent : le plugin Decky applique le correctif
à chaud sur les trois enfants, **mais le hub lui-même reste en `auto`** — or
c'est sa disparition qui emporte la manette.

Ligne de commande noyau (aucun paramètre USB ajouté) :

```
amd_iommu=off  amdgpu.lockup_timeout=5000,10000,10000,5000  ttm.pages_min=2097152
amdgpu.sched_hw_submission=4  amdgpu.dcdebugmask=0x20000  audit=0 loglevel=3 quiet
```

### Récupération au réveil — **installée**

`apex-resume-recover.service` est présente et **enabled** :

```ini
# /etc/systemd/system/apex-resume-recover.service
[Unit]
Description=OneXPlayer Apex gamepad resume recovery
After=suspend.target hibernate.target suspend-then-hibernate.target
[Service]
Type=oneshot
ExecStart=/bin/bash /var/lib/onexplayer-apex/apex-resume-recover.sh
[Install]
WantedBy=suspend.target hibernate.target suspend-then-hibernate.target
```

Dernier état : `ActiveState=inactive`, `ExecMainStatus=0`, 0 redémarrage.

## 7. Alimentation, thermique, TDP

| | |
|---|---|
| Batterie | **AEC714897-4S1P** Li-ion 4S1P, design **85 Wh**, pleine charge **87,09 Wh** |
| État | `Not charging`, **99 %** (86,25 Wh), secteur branché, 17,63 V |
| Cycles | **0** (compteur non implémenté par l'EC) |
| Limite de charge | `charge_control_end_threshold = 62` — **incohérent avec les 99 % constatés**, l'EC ne semble pas appliquer le plafond |

**TDP non réglable en watts.** Seul levier :
`/sys/firmware/acpi/platform_profile` — `low-power` / `balanced` / `performance`,
actuellement **`balanced`**.

Calibration mesurée (`~/apex-calib-perf.csv`), cran `performance` :

| cran | PPT repos | PPT moyen | PPT max | Tctl max | CPU moyen | ventilateur |
|---|---|---|---|---|---|---|
| performance | 23,8 W | **93,5 W** | 99,1 W | 90,9 °C | 3904 MHz | 5233 tr/min |

État au moment du relevé (machine allumée depuis 10 h 30, charge ~1,2) :

```
k10temp Tctl   45,9 °C     amdgpu edge  43,0 °C   PPT 15,09 W   sclk 1 GHz
acpitz         46,0 °C     NVMe         41,9 / 45,9 °C
iwlwifi        38,0 °C     ventilateur  4068 tr/min  (pwm1=0 %, pwm1_enable non exposé ici)
```

Le ventilateur tourne nettement plus vite qu'au relevé précédent (4068 contre
2575 tr/min) pour des températures à peine supérieures — cohérent avec une
machine en charge légère depuis 10 h, mais à surveiller.

### Pilote EC

`oxpec` **chargé** (avec `hid_oxp`), expose :

- hwmon `oxp_ec` (**hwmon5**) → `fan1_input`, `pwm1`
- `/sys/devices/platform/oxp-platform/` → **`tt_toggle`**

Autres modules pertinents : `xpad`, `hid_playstation`, `hid_nintendo`,
`hid_multitouch`, `led_class_multicolor`, `platform_profile` (via `amd_pmf`),
`i2c_hid_acpi`, `amdxdna`.

## 8. Stockage

| Périphérique | Détail |
|---|---|
| NVMe | **Samsung SSD 990 PRO 2 To**, firmware `1B2QJXD7` |
| microSD | `mmcblk0` 235,5 Go, btrfs, label `SD` |

**Le slot A/B a basculé** suite à la mise à jour SteamOS — les points de montage
ont changé de partition :

```
nvme0n1p1  256M  vfat  esp     /esp
nvme0n1p2   64M  vfat  efi     /efi      <- était p3
nvme0n1p4    5G  btrfs rootfs  /         <- était p5   (3,6G/5,0G = 75 %)
nvme0n1p6  256M  ext4  var     /var      <- était p7
nvme0n1p8  1,8T  ext4  home    /home     (548G/1,9T = 30 %)
```

`/` en **btrfs read-only SteamOS** (`steamos-readonly: enabled`), `/etc` en
overlay, offloads habituels sur `/home`.

Marge racine remontée à **1,3 Go libre (75 %)** — le ménage de la mise à jour a
aidé, mais ça reste serré pour un `pacman -S`.

## 9. Réseau — les deux liens sont actifs

| | |
|---|---|
| **eth0** | Realtek RTL8156 du dock — `192.168.1.19/24`, **2500 Mb/s full duplex**, IPv6 globale, métrique **100** |
| **wlan0** | Intel AX210 — `192.168.1.11/24`, **connecté à `Livebox-84C0` en 5,5 GHz / 160 MHz**, signal **-40 dBm**, rx 2268,5 Mbit/s (HE-MCS 11, NSS 2), métrique **600** |
| Bluetooth | Intel AX210 (`8087:0032`), `btusb` |
| Biométrie | FocalTech (`2808:c652`) — toujours **sans pilote** |

**Double route par défaut** vers 192.168.1.1 : eth0 l'emporte (métrique 100 <
600). À garder en tête pour tout diagnostic réseau — le trafic ne passe pas par
le Wi-Fi malgré son excellent lien.

## 10. Audio

PipeWire / WirePlumber. **Sortie active : `Nari Ultimate Mono`** (casque Razer) —
ce n'est plus les haut-parleurs internes.

| Sink | Cible |
|---|---|
| **Nari Ultimate Mono** ★ | casque Razer — sortie courante |
| Ryzen HD Audio Analog Stereo | **haut-parleurs internes** (cible de l'EQ du plugin) |
| Rembrandt Radeon HD Audio Digital Stereo (HDMI) | audio DP/HDMI (`c5:00.1`) |

2 loopbacks WirePlumber actifs (`loopback-2346-19` / `-20`). Le sink HDMI
`hdmi-stereo-extra2` est référencé côté vidéo.

> L'EQ haut-parleurs du plugin cible `alsa_output.pci-0000_c5_00.6` : elle n'a
> **aucun effet** tant que la sortie active est le casque USB.

## 11. Périphériques HID branchés

- **Razer Nari Ultimate** (`1532:051a`) — casque
- **Razer Ornata Chroma** (`1532:021e`) — clavier
- **Razer Naga Pro** (`1532:0090`, dongle sans fil) — souris
- **Razer Goliathus Extended Chroma** (`1532:0c02`) — tapis RGB, s'expose en clavier *et* souris
- **Generic USB Audio** (Realtek du dock) — s'expose aussi en HID Consumer Control
- Écran tactile interne **NVTK0603:00** (Novatek, i2c-hid)

**36 périphériques d'entrée**, numérotation `event` redescendue sous 32 (plus de
`event256+` — la Naga Pro filaire, l'adaptateur Xbox sans fil, la webcam et le
lecteur de cartes SANHO ont été débranchés).

## 12. Pile logicielle

| | |
|---|---|
| OS | **SteamOS 3.8.26**, build `20260827.1`, branche `stable` |
| Noyau | **6.18.46-valve1-1-neptune-618** (`linux-neptune-618` 6.18.46.valve1-1) |
| Session | **Wayland / KDE Plasma** (Bureau) — `kwin_wayland` + `plasmashell` + `steamos-manager` |
| Gamescope | 3.16.23.5-1 |
| Steam | `steam-jupiter-stable` 1.0.0.85-9.2 |
| Decky Loader | **v3.2.8-pre1** |
| Plugins Decky | **Junk-Store**, **OneXPlayer Apex SteamOS Tools** (ce dépôt) |
| Conteneur Claude | distrobox `claude` — **Ubuntu 24.04.4 LTS**, podman rootless, `/home/deck` partagé |
| Locale | système `en_US.UTF-8`, outils en `fr_FR` (⚠ virgule décimale → `LC_ALL=C` dans les scripts) |
| Flatpaks | Brave 1.95, Discord, Spotify, Thunderbird ESR 140, VLC, LibreOffice 26.8, FreeCAD 1.1.3, ProtonPlus, protontricks, legendary, DistroShelf, Gear Lever, AppImage Pool |

Aucune unité systemd en échec.

## 13. Écarts depuis le relevé du 2026-08-26

| Domaine | Avant (26/08) | Maintenant (14/09) |
|---|---|---|
| **SteamOS** | 3.8.25 / build 20260807.2 | **3.8.26 / build 20260827.1** |
| **Noyau** | 6.18.42-valve2 | **6.18.46-valve1** |
| **Slot A/B** | rootfs p5, var p7, efi p3 | **basculé** : rootfs p4, var p6, efi p2 |
| **Dock** | VIA Labs USB-C (xHCI natif) | **i-tec Thunderbolt 4 Goshen Ridge, PCIe tunnelé** |
| **Lien dock** | USB 3.1 10 Gbit/s | **TB4 à 40 Gb/s** (2 voies × 20, conforme) |
| **Connecteurs DP** | DP-9 / DP-10 (11 exposés) | **DP-5 / DP-6 (8 exposés), et ils s'échangent entre deux boots** |
| **Écran interne** | désactivé (docké) | **actif**, 3 écrans simultanés |
| **Ethernet** | ASIX AX88179A — 1 GbE | **Realtek RTL8156 — 2,5 GbE à 2500 Mb/s** |
| **Wi-Fi** | `DOWN` | **connecté** 5,5 GHz / 160 MHz, -40 dBm |
| **Sortie audio** | haut-parleurs internes | **casque Nari Ultimate** |
| **Résilience réveil** | rien d'installé | **`apex-resume-recover.service` enabled** |
| **EDID SKG** | 1.3 / 256 o, moy. max 283 nits | **1.4 / 384 o, moy. max 400 nits** |
| **/ (rootfs)** | 83 % (782 Mo libres) | **75 % (1,3 Go libres)** |
| **/home** | 316 Go | **548 Go** |
| **Ventilateur repos** | 2575 tr/min | **4068 tr/min** |
| **Débranché depuis** | — | webcam, Naga Pro filaire, adaptateur Xbox sans fil, lecteur SANHO RD80, audio GeneralPlus |
| **Inchangé** | règle udev absente, hub interne en `auto`, VRAM 16 Go, TDP via `platform_profile`, seuil de charge 62 %, oxpec chargé | idem |

## 14. Identifiants à retenir

```
DMI                ONE-NETBOOK / ONEXPLAYER APEX
Hub interne        1a86:8091   QinHeng                    -> 1-1        (control=auto !)
Manette interne    045e:028e   Xbox 360 pad               -> 1-1.3, js0
HID boutons OXP    1a2c:b001   ONE NETBOOK                -> 1-1.1
Clavier interne    1a86:fe00   HID                        -> 1-1.2
xHCI interne       0000:c5:00.4                           (bus USB 1)
xHCI dock          0000:c7:00.3                           (bus USB 5 + 6)
Routeurs USB4      0000:c7:00.5 (domain0, dock) / 0000:c7:00.6 (domain1, vide)
Dock TB4           3188:c141   i-tec TB4DUALDPDOCKPDPRO   -> tb 0-2, NVM 43.1, 40 Gb/s (2x20)
Ethernet dock      0bda:8156   Realtek RTL8156 2.5GbE     -> eth0, r8152
iGPU               0000:c5:00.0  1002:1586                (amdgpu, card0)
NPU                0000:c6:00.1  1022:17F0                (amdxdna, /dev/accel/accel0)
Panneau interne    BOE NS080WUM-LX1  8,0" 1920x1200@120Hz  (eDP-1, portrait, scale 1.2)
Externe HDR        SKG H32S17        32" reel (EDID dit 27" : DTD errone) 2560x1440@120
Externe secondaire Acer EB321HQU     31,5" 2560x1440@60
UUID KDE ecrans    cc91b2c1=SKG  cbb8d055=Acer  802e2c0c=interne  (stables, contrairement a DP-n)
EC hwmon           /sys/class/hwmon/hwmon5  (oxp_ec)
EC plateforme      /sys/devices/platform/oxp-platform/tt_toggle
TDP                /sys/firmware/acpi/platform_profile     (low-power|balanced|performance)
Seuil de charge    /sys/class/power_supply/BATT/charge_control_end_threshold = 62
Service réveil     apex-resume-recover.service -> /var/lib/onexplayer-apex/apex-resume-recover.sh
Diag dock          ~/tb4-etat.sh
```
