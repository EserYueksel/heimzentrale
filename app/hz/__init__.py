"""Heimzentrale - Zustand und Pflege der Raspberry Pis im Heimnetz.

Module:
  config     Einstellungen (heimzentrale.conf, ntfy.conf)
  db         SQLite-Datenbank und Umstellungen
  fmt        Zahlen und Zeiten auf Deutsch
  metrics    Werte aus einer Meldung lesen
  reports    Meldungen der Pis speichern
  nettip     Blockhoehe des Bitcoin-Netzes
  checks     Was auffaellt (Hinweise, Warnungen, Probleme)
  notify     Handy-Meldungen ueber ntfy
  alerts     Wann aufs Handy gemeldet wird
  core       Bitcoin-Core-Versionen
  tasks      Auftraege an die Agenten (Update, Programme entfernen), PIN
  inventory  Installierte Programme je Pi
  status     Antworten fuer die Seite (Zustand, Verlauf)
  web        HTTP-Server
  worker     Hintergrund-Aufgaben
"""

VERSION = "2.0.1"
