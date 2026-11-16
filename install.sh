#!/bin/bash
# Heimzentrale - Installer fuer Raspberry Pi OS / Debian
#
#   Heimzentrale einrichten oder aktualisieren (auf dem Pi, der die Seite zeigen soll):
#     curl -fsSL https://raw.githubusercontent.com/EserYueksel/heimzentrale/main/install.sh | sudo bash
#
#   Nur den Agenten auf einem weiteren Pi einrichten (den fertigen Befehl zeigt die Seite unter "Pi hinzufuegen"):
#     curl -fsSL http://ADRESSE:8088/install.sh | sudo bash -s -- agent http://ADRESSE:8088 SCHLUESSEL
#
#   Agenten wieder entfernen:
#     sudo bash install.sh agent-entfernen
#
# Was der Installer tut, steht unten in einfachen Schritten. Er fragt nach, bevor er etwas Groesseres tut.
set -euo pipefail

REPO="EserYueksel/heimzentrale"
BRANCH="${HZ_BRANCH:-main}"
PORT="${HZ_PORT:-8088}"
AGENT_BIN=/usr/local/bin/heimzentrale-agent
AGENT_CONF=/etc/heimzentrale-agent.conf
CRON_LINE="* * * * * $AGENT_BIN > /dev/null 2>&1"

say()  { printf '\n\033[1m%s\033[0m\n' "$*"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
info() { printf '  %s\n' "$*"; }
die()  { printf '\n\033[31mFehler:\033[0m %s\n' "$*" >&2; exit 1; }
ask()  { # Frage ueber das Terminal (auch wenn das Skript per curl | bash kommt)
  local prompt=$1 var=$2 secret=${3:-}
  local answer=""
  if ! (: < /dev/tty) 2> /dev/null; then printf -v "$var" '%s' ""; return 0; fi  # kein Terminal: nichts fragen
  if [ -n "$secret" ]; then read -rsp "$prompt" answer < /dev/tty || true; echo; else read -rp "$prompt" answer < /dev/tty || true; fi
  printf -v "$var" '%s' "$answer"
}

[ "$(id -u)" -eq 0 ] || die "Bitte mit sudo starten."
command -v python3 > /dev/null || die "python3 fehlt. Installieren mit: sudo apt install -y python3"
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' || die "python3 ist zu alt (mindestens 3.9)."

# ---------------------------------------------------------------- Agent

remove_old_melder() {
  # Version 1 hatte einen Bash-Melder in der crontab eines Benutzers - der Agent ersetzt ihn
  local f u
  for f in /var/spool/cron/crontabs/*; do
    [ -f "$f" ] || continue
    u=$(basename "$f")
    if crontab -u "$u" -l 2> /dev/null | grep -q heimzentrale-melder; then
      crontab -u "$u" -l | grep -v heimzentrale-melder | crontab -u "$u" -
      ok "Alten Melder aus der crontab von $u entfernt (der Agent übernimmt)."
    fi
  done
}

install_agent() { # URL TOKEN [lokale Datei]
  local url=${1%/} token=$2 src=${3:-} tmp
  [[ "$url" =~ ^https?://[^[:space:]]+$ ]] || die "Ungültige Adresse: $url"
  [[ "$token" =~ ^[A-Za-z0-9]{8,128}$ ]] || die "Ungültiger Schlüssel."
  say "Agent einrichten"
  tmp=$(mktemp)
  if [ -n "$src" ]; then
    cp "$src" "$tmp"
  else
    curl -fsSL -o "$tmp" "$url/agent/heimzentrale-agent" || die "Agent nicht ladbar von $url - stimmt die Adresse und läuft die Heimzentrale?"
  fi
  head -n 1 "$tmp" | grep -q python3 || die "Die geladene Datei ist kein Agent."
  install -m 0755 -o root -g root "$tmp" "$AGENT_BIN"
  rm -f "$tmp"
  ok "Agent installiert: $AGENT_BIN ($("$AGENT_BIN" version))"

  # Einstellungen: HZ_URL/HZ_TOKEN setzen, eigene Zusatzzeilen (z. B. DISKS) behalten
  touch "$AGENT_CONF"
  chmod 0600 "$AGENT_CONF"
  { grep -v -E '^(HZ_URL|HZ_TOKEN)=' "$AGENT_CONF" || true; printf 'HZ_URL=%s\nHZ_TOKEN=%s\n' "$url" "$token"; } > "$AGENT_CONF.neu"
  mv "$AGENT_CONF.neu" "$AGENT_CONF"
  chmod 0600 "$AGENT_CONF"
  ok "Einstellungen: $AGENT_CONF"

  if ! command -v crontab > /dev/null; then
    info "Installiere cron …"
    apt-get install -y cron > /dev/null
  fi
  remove_old_melder
  { crontab -l 2> /dev/null | grep -v heimzentrale-agent || true; echo "$CRON_LINE"; } | crontab -
  ok "Läuft jede Minute (crontab von root)."

  if "$AGENT_BIN" pruefen; then
    "$AGENT_BIN" melden > /dev/null && ok "Erste Meldung gesendet."
    "$AGENT_BIN" programme > /dev/null && ok "Programmliste gesendet."
  else
    info "Die Heimzentrale ist gerade nicht erreichbar. Der Agent versucht es jede Minute wieder."
  fi
}

remove_agent() {
  say "Agent entfernen"
  { crontab -l 2> /dev/null | grep -v heimzentrale-agent || true; } | crontab -
  ok "Zeitplan entfernt."
  rm -f "$AGENT_BIN" && ok "Programm entfernt."
  rm -f "$AGENT_CONF" && ok "Einstellungen entfernt."
  info "Arbeitsdaten bleiben in /var/lib/heimzentrale-agent (z. B. Sicherungen). Bei Bedarf von Hand löschen."
}

# ---------------------------------------------------------------- Heimzentrale

find_install() {
  local d
  for d in /DATA/AppData/heimzentrale /opt/heimzentrale; do
    [ -f "$d/app/server.py" ] && { echo "$d"; return; }
  done
  [ -d /DATA/AppData ] && echo /DATA/AppData/heimzentrale || echo /opt/heimzentrale
}

fetch_source() { # Ordner mit app/ und install.sh
  # Aus einem geklonten Ordner gestartet: dessen Dateien nehmen. Per curl | bash: von GitHub laden.
  local self=${BASH_SOURCE[0]:-} here="" tmp
  if [ -n "$self" ] && [ -f "$self" ]; then
    here=$(cd "$(dirname "$self")" && pwd)
    if [ -f "$here/app/server.py" ]; then echo "$here"; return; fi
  fi
  tmp=$(mktemp -d)
  curl -fsSL "https://github.com/$REPO/archive/refs/heads/$BRANCH.tar.gz" | tar -xz -C "$tmp" \
    || die "Herunterladen von GitHub fehlgeschlagen."
  find "$tmp" -mindepth 1 -maxdepth 1 -type d | head -n 1
}

conf_get() { grep -E "^$1=" "$2" 2> /dev/null | tail -n 1 | cut -d= -f2- || true; }

running_version() { # Version, die gerade auf dem Port antwortet (leer = keine Antwort)
  curl -fsS --max-time 5 "http://localhost:$PORT/api/health" 2> /dev/null \
    | python3 -c 'import json, sys; print(json.load(sys.stdin).get("version", ""))' 2> /dev/null || true
}

lan_ip() { # Adresse im Heimnetz: die, ueber die der Pi ins Internet geht (nicht die von Docker-Netzen)
  local a
  a=$(ip -4 route get 1.1.1.1 2> /dev/null | awk '{for (i = 1; i < NF; i++) if ($i == "src") { print $(i + 1); exit }}')
  [ -n "$a" ] || a=$(hostname -I 2> /dev/null | tr ' ' '\n' | grep -v -E '^(172\.(1[6-9]|2[0-9]|3[01])\.|127\.)' | grep -E '^[0-9.]+$' | head -n 1)
  echo "$a"
}

install_server() {
  local dir src mode token ip pin pin2 topic version
  dir=$(find_install)
  say "Heimzentrale einrichten in $dir"
  src=$(fetch_source)
  [ -f "$src/app/server.py" ] || die "Programmdateien nicht gefunden."

  # Betriebsart: vorhandenes Docker-Compose behalten, sonst Docker wenn da, sonst systemd
  if [ -f "$dir/docker-compose.yml" ]; then mode=docker
  elif docker compose version > /dev/null 2>&1; then mode=docker
  else mode=systemd; fi
  info "Betriebsart: $mode"

  mkdir -p "$dir/data"
  if [ -d "$dir/app" ]; then
    rm -rf "$dir/app.vorher"
    mv "$dir/app" "$dir/app.vorher"
    ok "Bisherige Version gesichert in $dir/app.vorher"
  fi
  cp -r "$src/app" "$dir/app"
  cp "$src/install.sh" "$dir/app/install.sh"
  version=$(python3 -B -c "import sys; sys.path.insert(0, '$dir/app'); import hz; print(hz.VERSION)")
  ok "Programm $version kopiert."

  # Einstellungen
  local conf="$dir/data/heimzentrale.conf"
  touch "$conf"
  token=$(conf_get HZ_TOKEN "$conf")
  if [ -z "$token" ]; then
    token=$(python3 -c 'import secrets; print(secrets.token_hex(16))')
    printf 'HZ_TOKEN=%s\n' "$token" >> "$conf"
    ok "Neuer Schlüssel für die Agenten erzeugt."
  fi
  ip=$(lan_ip)
  if [ -z "$(conf_get PUBLIC_URL "$conf")" ] && [ -n "$ip" ]; then
    printf 'PUBLIC_URL=http://%s:%s\n' "$ip" "$PORT" >> "$conf"
  fi
  if [ -z "$(conf_get UPDATE_PIN_SHA256 "$conf")" ]; then
    info "Die PIN schützt die Knöpfe zum Aktualisieren und Entfernen (4 bis 8 Ziffern)."
    ask "  Neue PIN: " pin secret
    ask "  PIN wiederholen: " pin2 secret
    if [[ "$pin" =~ ^[0-9]{4,8}$ ]] && [ "$pin" = "$pin2" ]; then
      printf 'UPDATE_PIN_SHA256=%s\n' "$(printf '%s' "$pin" | sha256sum | cut -d' ' -f1)" >> "$conf"
      ok "PIN gespeichert."
    else
      info "Keine gültige PIN – die Knöpfe bleiben gesperrt. Später: sudo bash $dir/app/install.sh pin"
    fi
  fi
  if [ ! -s "$dir/data/ntfy.conf" ] && [ -z "$(conf_get NTFY_TOPIC "$conf")" ]; then
    info "Handy-Meldungen über die App ntfy: Kanalname eingeben (leer lassen = keine Meldungen)."
    ask "  ntfy-Kanal: " topic
    if [[ "$topic" =~ ^[A-Za-z0-9_-]{6,64}$ ]]; then
      printf 'NTFY_TOPIC=%s\n' "$topic" > "$dir/data/ntfy.conf"
      ok "Kanal gespeichert. In der ntfy-App denselben Namen abonnieren."
    fi
  fi
  chmod 0640 "$conf"

  # Starten
  if [ "$mode" = docker ]; then
    if [ ! -f "$dir/docker-compose.yml" ]; then
      sed "s#/DATA/AppData/heimzentrale#$dir#g; s#8088:8088#$PORT:8088#" "$src/docker-compose.yml" > "$dir/docker-compose.yml"
    fi
    (cd "$dir" && docker compose up -d > /dev/null && docker compose restart > /dev/null)
    ok "Container läuft (docker compose)."
  else
    id heimzentrale > /dev/null 2>&1 || useradd --system --no-create-home --shell /usr/sbin/nologin heimzentrale
    chown -R heimzentrale:heimzentrale "$dir/data"
    cat > /etc/systemd/system/heimzentrale.service <<EOF
[Unit]
Description=Heimzentrale
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=/usr/bin/python3 -u $dir/app/server.py
Environment=HZ_DATA=$dir/data PORT=$PORT
User=heimzentrale
Restart=on-failure
NoNewPrivileges=true
ProtectSystem=full
ProtectHome=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload
    systemctl enable heimzentrale > /dev/null 2>&1
    systemctl restart heimzentrale
    ok "Dienst läuft (systemd: heimzentrale)."
  fi

  # Warten, bis die NEUE Version antwortet (nicht noch die alte)
  local _ running=""
  for _ in $(seq 1 45); do
    running=$(running_version)
    [ "$running" = "$version" ] && break
    sleep 1
  done
  [ -n "$running" ] || die "Die Heimzentrale antwortet nicht auf Port $PORT."
  if [ "$running" != "$version" ]; then
    [ "$mode" = docker ] && info "Neu starten mit: cd $dir && sudo docker compose restart"
    [ "$mode" = systemd ] && info "Neu starten mit: sudo systemctl restart heimzentrale"
    die "Auf Port $PORT läuft noch Version $running statt $version."
  fi
  ok "Version $version antwortet auf Port $PORT."

  install_agent "http://localhost:$PORT" "$token" "$dir/app/agent/heimzentrale-agent"
  desktop_shortcut

  say "Fertig."
  info "Seite: http://${ip:-localhost}:$PORT  (auf diesem Pi: http://localhost:$PORT)"
  info "Weitere Pis: auf der Seite \"Pi hinzufügen\" – dort steht der fertige Befehl."
}

desktop_shortcut() {
  # Eintrag im Programm-Menue fuer den Benutzer, der sudo aufgerufen hat (nur mit Desktop)
  local user=${SUDO_USER:-} home
  [ -n "$user" ] && [ "$user" != root ] || return 0
  home=$(getent passwd "$user" | cut -d: -f6)
  [ -d "$home/.local/share" ] || [ -d /usr/share/applications ] || return 0
  [ -d /usr/share/applications ] || return 0
  sudo -u "$user" mkdir -p "$home/.local/bin" "$home/.local/share/applications" "$home/.local/share/icons"
  curl -fsS -o "$home/.local/share/icons/heimzentrale.svg" "http://localhost:$PORT/favicon.svg" || return 0
  cat > "$home/.local/bin/heimzentrale" <<EOF
#!/bin/sh
# Heimzentrale in einem eigenen Fenster oeffnen
URL=http://localhost:$PORT
for b in chromium chromium-browser google-chrome; do
  command -v "\$b" >/dev/null 2>&1 && exec "\$b" --app="\$URL"
done
for b in firefox firefox-esr; do
  command -v "\$b" >/dev/null 2>&1 && exec "\$b" --new-window "\$URL"
done
exec xdg-open "\$URL"
EOF
  printf '%s\n' '[Desktop Entry]' 'Type=Application' 'Name=Heimzentrale' 'Comment=Zustand und Pflege der Raspberry Pis' \
    "Exec=$home/.local/bin/heimzentrale" "Icon=$home/.local/share/icons/heimzentrale.svg" 'Terminal=false' \
    'Categories=Utility;Network;' > "$home/.local/share/applications/heimzentrale.desktop"
  chmod +x "$home/.local/bin/heimzentrale"
  chown "$user": "$home/.local/bin/heimzentrale" "$home/.local/share/applications/heimzentrale.desktop" "$home/.local/share/icons/heimzentrale.svg"
  ok "Eintrag 'Heimzentrale' im Programm-Menü für $user angelegt."
}

set_pin() {
  local dir conf pin pin2
  dir=$(find_install)
  conf="$dir/data/heimzentrale.conf"
  [ -f "$conf" ] || die "Keine Heimzentrale gefunden ($conf fehlt)."
  ask "Neue PIN (4 bis 8 Ziffern): " pin secret
  ask "PIN wiederholen: " pin2 secret
  [[ "$pin" =~ ^[0-9]{4,8}$ ]] || die "Nur 4 bis 8 Ziffern."
  [ "$pin" = "$pin2" ] || die "Die beiden Eingaben sind verschieden."
  { grep -v '^UPDATE_PIN_SHA256=' "$conf" || true; printf 'UPDATE_PIN_SHA256=%s\n' "$(printf '%s' "$pin" | sha256sum | cut -d' ' -f1)"; } > "$conf.neu"
  mv "$conf.neu" "$conf"
  ok "PIN gespeichert. Sie gilt spätestens nach einer Minute."
}

case "${1:-server}" in
  server|"") install_server ;;
  agent) [ $# -ge 3 ] || die "Aufruf: install.sh agent URL SCHLUESSEL"; install_agent "$2" "$3" ;;
  agent-entfernen) remove_agent ;;
  pin) set_pin ;;
  *) die "Unbekannt: $1 (möglich: server, agent URL SCHLUESSEL, agent-entfernen, pin)" ;;
esac
