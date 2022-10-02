# PHAL plugin - Balena Wifi Setup-

this plugin provides a balena interface for the wifi setup and is part of a larger collection of Wifi client plugins

Balena creates a hotspot you can connect to and set your credentials, this is the default option for devices without a GUI

this plugin replaces the old [skill-balena-wifi-setup](https://github.com/OpenVoiceOS/skill-balena-wifi-setup)


# Install

`pip install ovos-PHAL-plugin-balena-wifi`

# Events

```python

# WIFI Plugin Registeration and Activation Specific Events        
self.bus.on("ovos.phal.wifi.plugin.stop.setup.event", self.handle_stop_setup)
self.bus.on("ovos.phal.wifi.plugin.client.registered", self.handle_registered)
self.bus.on("ovos.phal.wifi.plugin.client.deregistered", self.handle_deregistered)
self.bus.on("ovos.phal.wifi.plugin.client.registration.failure", self.handle_registration_failure)
self.bus.on("ovos.phal.wifi.plugin.alive", self.register_client)

```

# Configuration

You can change a few parameters to customize the setup assets, you can change some Hotspot details, dialogs and GUI strings

```json
{
  "ssid": "OVOS",
  "portal": "start dot openvoiceos dot com",
  "device_name": "OVOS Device",
  "image_connect_ap":  "1_phone_connect-to-ap.png",
  "image_choose_wifi":  "3_phone_choose-wifi.png"
}
```
