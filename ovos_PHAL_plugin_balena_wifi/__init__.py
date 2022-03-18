from os.path import join, dirname

import pexpect
import random
import subprocess
from mycroft_bus_client.message import Message, dig_for_message
from ovos_plugin_manager.phal import PHALPlugin
from ovos_utils import create_daemon
from ovos_utils.enclosure.api import EnclosureAPI
from ovos_utils.gui import GUIInterface
from ovos_utils.log import LOG
from ovos_utils.network_utils import is_connected
from time import sleep


class BalenaWifiSetupPlugin(PHALPlugin):
    def __init__(self, bus=None, config=None):
        super().__init__(bus=bus, name="ovos-PHAL-plugin-balena-wifi", config=config)
        self.monitoring = False
        self.in_setup = False
        self.connected = False
        self.wifi_process = None
        self.debug = False  # dev setting, VERY VERBOSE DIALOGS
        self.ssid = "OVOS"
        self.pswd = None
        self.grace_period = 45
        self.time_between_checks = 30  # seconds
        self.mycroft_ready = False
        self.wifi_command = "sudo /usr/local/sbin/wifi-connect --portal-ssid {ssid}"
        if self.pswd:
            self.wifi_command += " --portal-passphrase {pswd}"
        self.color = "#FF0000"
        self.stop_on_internet = False
        self.timeout_after_internet = 90

        self.bus.on("mycroft.internet.connected", self.handle_internet_connected)

        self.enclosure = EnclosureAPI(bus=self.bus, skill_id=self.name)
        self.gui = GUIInterface(bus=self.bus, skill_id=self.name)
        self.start_internet_check()

    # internet watchdog
    def start_internet_check(self):
        create_daemon(self._watchdog)

    def stop_internet_check(self):
        self.monitoring = False

    def _watchdog(self):
        try:
            self.monitoring = True
            LOG.info("Wifi watchdog started")
            output = subprocess.check_output("nmcli connection show",
                                             shell=True).decode("utf-8")
            if "wifi" in output:
                LOG.info("Detected previously configured wifi, starting "
                         "grace period to allow it to connect")
                sleep(self.grace_period)
            while self.monitoring:
                if self.in_setup:
                    sleep(1)  # let setup do it's thing
                    continue

                if not is_connected():
                    LOG.info("NO INTERNET")
                    if not self.is_connected_to_wifi():
                        LOG.info("LAUNCH SETUP")
                        try:
                            self.launch_wifi_setup()  # blocking
                        except Exception as e:
                            LOG.exception(e)
                    else:
                        LOG.warning("CONNECTED TO WIFI, BUT NO INTERNET!!")

                sleep(self.time_between_checks)
        except Exception as e:
            LOG.error("Wifi watchdog crashed unexpectedly")
            LOG.exception(e)

    # wifi setup
    @staticmethod
    def get_wifi_ssid():
        SSID = None
        try:
            SSID = subprocess.check_output(["iwgetid", "-r"]).strip()
        except subprocess.CalledProcessError:
            # If there is no connection subprocess throws a 'CalledProcessError'
            pass
        return SSID

    @staticmethod
    def is_connected_to_wifi():
        return BalenaWifiSetupPlugin.get_wifi_ssid() is not None

    def launch_wifi_setup(self):
        if not self.in_setup:
            self.bus.emit(Message("ovos.wifi.setup.started"))
        self.stop_setup()
        self.in_setup = True
        self.wifi_process = pexpect.spawn(
            self.wifi_command.format(ssid=self.ssid)
        )
        # https://github.com/pexpect/pexpect/issues/462
        self.wifi_process.delayafterclose = 1
        self.wifi_process.delayafterterminate = 1
        prev = ""
        restart = False
        if self.debug:
            self.speak_dialog("debug_start_setup")

        while self.in_setup:
            try:
                out = self.wifi_process.readline().decode("utf-8").strip()
                if out == prev:
                    continue
                prev = out
                if out.startswith("Access points: "):
                    aps = list(out.split("Access points: ")[-1])
                    LOG.info(out)
                    if self.debug:
                        self.speak_dialog("debug_wifi_scanned")
                elif out.startswith("Starting access point..."):
                    if self.debug:
                        self.speak_dialog("debug_ap_start")
                elif out.startswith("Access point ") and \
                        out.endswith("created"):
                    self.prompt_to_join_ap()
                    if self.debug:
                        self.speak_dialog("debug_ap_created")
                elif out.startswith("Starting HTTP server on"):
                    LOG.debug(out)
                    if self.debug:
                        self.speak_dialog("debug_http_started")
                elif out.startswith("Stopping access point"):
                    if self.debug:
                        self.speak_dialog("debug_ap_stop")
                elif out.startswith("Access point ") and \
                        out.endswith("stopped"):
                    if self.debug:
                        self.speak_dialog("debug_ap_stopped")
                elif out == "User connected to the captive portal":
                    LOG.info(out)
                    self.prompt_to_select_network()
                    if self.debug:
                        self.speak_dialog("debug_user_connected")
                elif out.startswith("Connecting to access point"):
                    if self.debug:
                        self.speak_dialog("debug_connecting")
                elif out.startswith("Internet connectivity established"):
                    LOG.info(out)
                    self.report_setup_complete()
                    if self.debug:
                        self.speak_dialog("debug_wifi_connected")
                elif "Error" in out or "[Errno" in out:
                    LOG.error(out)
                    self.report_setup_failed()

                    # TODO figure out at least the errors handled gracefully
                    accepted_errors = [
                        "Password length should be at least 8 characters"
                    ]
                    for e in accepted_errors:
                        if e in out:
                            continue
                    else:
                        restart = True
                        break

                if self.debug:
                    LOG.debug(out)
            except pexpect.exceptions.EOF:
                # exited
                LOG.info("Exited wifi setup process")
                break
            except pexpect.exceptions.TIMEOUT:
                # nothing happened for a while
                pass
            except KeyboardInterrupt:
                break
            except Exception as e:
                LOG.exception(e)
                break
        self.stop_setup()
        if restart:
            # handle bugs in balena, sometimes it fails to come back up
            # seems to happen on
            # Error: Getting access points failed
            self.launch_wifi_setup()
        elif self.debug:
            self.speak_dialog("debug_end_setup")

    # bus events
    def handle_internet_connected(self, message=None):
        """System came online later after booting."""
        self.enclosure.mouth_reset()
        # sync clock as soon as we have internet
        self.bus.emit(Message("system.ntp.sync"))
        self.stop_setup()  # just in case
        self.gui.release()

    # GUI events
    def prompt_to_join_ap(self, message=None):
        """Provide instructions for setting up wifi."""
        self.manage_setup_display("join-ap", "prompt")
        self.speak_dialog("wifi_intro_2")
        # allow GUI to linger around for a bit, will block the wifi setup loop
        sleep(2)

    def prompt_to_select_network(self, message=None):
        """Prompt user to select network and login."""
        self.manage_setup_display("select-network", "prompt")
        self.speak_dialog("wifi_intro_3")
        # allow GUI to linger around for a bit, will block the wifi setup loop
        sleep(2)

    def report_setup_complete(self, message=None):
        """Wifi setup complete, network is connected."""
        # once first connected to internet increase time between checks
        self.connected = True
        self.time_between_checks = self.timeout_after_internet
        # stop watchdog on internet connection
        if self.stop_on_internet:
            self.monitoring = False
        self.manage_setup_display("setup-completed", "status")
        # allow GUI to linger around for a bit, will block the wifi setup loop
        sleep(5)
        self.bus.emit(Message("ovos.wifi.setup.completed"))
        # pairing skill should take over now
        self.gui.release()

    def report_setup_failed(self, message=None):
        """Wifi setup failed"""
        self.manage_setup_display("setup-failed", "status")
        self.speak_dialog("debug_wifi_error")
        # allow GUI to linger around for a bit, will block the wifi setup loop
        sleep(2)

    def manage_setup_display(self, state, page_type):
        self.gui.clear()
        page = join(dirname(__file__), "ui", "NetworkLoader.qml")
        if state == "join-ap" and page_type == "prompt":
            self.gui["image"] = "1_phone_connect-to-ap.png"
            self.gui["label"] = "Connect to the Wi-Fi network"
            self.gui["highlight"] = self.ssid
            self.gui["color"] = self.color
            self.gui["page_type"] = "Prompt"
            self.gui.show_page(page, override_animations=True, override_idle=True)
        elif state == "select-network" and page_type == "prompt":
            self.gui["image"] = "3_phone_choose-wifi.png"
            self.gui["label"] = "Select local Wi-Fi network to connect"
            self.gui["highlight"] = "OVOS Device"
            self.gui["color"] = self.color
            self.gui["page_type"] = "Prompt"
            self.gui.show_page(page, override_animations=True, override_idle=True)
        elif state == "setup-completed" and page_type == "status":
            self.gui["image"] = "icons/check-circle.svg"
            self.gui["label"] = "Connected"
            self.gui["highlight"] = ""
            self.gui["color"] = "#40DBB0"
            self.gui["page_type"] = "Status"
            self.gui.show_page(page, override_animations=True)
        elif state == "setup-failed" and page_type == "status":
            self.gui["image"] = "icons/times-circle.svg"
            self.gui["label"] = "Connection Failed"
            self.gui["highlight"] = ""
            self.gui["color"] = "#FF0000"
            self.gui["page_type"] = "Status"
            self.gui.show_page(page, override_animations=True)

    # cleanup
    def stop_setup(self):
        if self.wifi_process is not None:
            try:
                if self.wifi_process.isalive():
                    LOG.debug("terminating wifi setup process")
                    self.wifi_process.sendcontrol('c')
                    sleep(1)
                    self.wifi_process.close()
                    sleep(1)
                if self.wifi_process.isalive():
                    LOG.warning('wifi setup did not exit gracefully.')
                    self.wifi_process.close(force=True)
                    sleep(1)
                    if self.wifi_process.isalive():
                        LOG.warning('trying to terminate wifi setup process')
                        self.wifi_process.terminate()
                        sleep(1)
                else:
                    LOG.debug('wifi setup exited gracefully.')
            except Exception as e:
                LOG.exception(e)
        self.wifi_process = None
        self.in_setup = False

    def shutdown(self):
        self.monitoring = False
        self.bus.remove("mycroft.internet.connected", self.handle_internet_connected)
        self.stop_setup()
        super().shutdown()

    # speech
    @property
    def lang(self):
        return self.config.get("lang") or \
               self.config_core.get("lang") or \
               "en-us"

    def speak_dialog(self, key):
        """ Speak a random sentence from a dialog file.
        Args:
            key (str): dialog file key (e.g. "hello" to speak from the file
                                        "locale/en-us/hello.dialog")
        """
        dialog_file = join(dirname(__file__), "locale", self.lang, key + ".dialog")
        with open(dialog_file) as f:
            utterances = [u for u in f.read().split("\n")
                          if u.strip() and not u.startswith("#")]
        utterance = random.choice(utterances)
        meta = {'dialog': key,
                'skill': self.name}
        data = {'utterance': utterance,
                'expect_response': False,
                'meta': meta,
                'lang': self.lang}
        message = dig_for_message()
        m = message.forward("speak", data) if message else Message("speak", data)
        m.context["skill_id"] = self.name
        self.bus.emit(m)
