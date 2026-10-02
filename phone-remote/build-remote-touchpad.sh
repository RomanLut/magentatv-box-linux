#!/bin/bash
# build-remote-touchpad.sh (checks/41, "Phone remote"): cross-build remote-touchpad (unrud/remote-touchpad,
# GPL-3.0) for the box in the debian:bookworm image of games-20260924/build-cores.sh, so the binary
# links against the box's glibc (2.36). Only the X11 backend (-tags x11, XTest into the TV's display
# :0): our kernel has no uinput (CONFIG_INPUT_UINPUT, no /dev/uinput), and everything the phone
# controls runs on that X display. cgo is needed anyway by the terminal package. Go and the source are fetched inside the container, pinned
# and checked; the result stays in the Docker volume mrg5-phone-remote (never on the Windows disk,
# where Avast removes cross-compiled ARM binaries). Send it to the box with
#   docker run --rm -v mrg5-phone-remote:/out mrg5-cores-bookworm cat /out/remote-touchpad |
#     ssh root@<box> 'cat > /usr/local/bin/remote-touchpad && chmod 755 /usr/local/bin/remote-touchpad'
# Run from Git Bash with Docker Desktop running.
set -e
export MSYS_NO_PATHCONV=1
GO=go1.26.8.linux-amd64.tar.gz
GO_SHA=d0f743b33e8d8945e6b1f432edd15785c70507121d6e2a723b21285eddf8b57b
TAG=v1.5.5
COMMIT=d7cd061

docker volume create mrg5-phone-remote >/dev/null
docker run --rm -i -v mrg5-phone-remote:/out -e GO=$GO -e GO_SHA=$GO_SHA -e TAG=$TAG -e COMMIT=$COMMIT \
    mrg5-cores-bookworm bash -s <<'EOF'
set -e
apt-get update -qq && apt-get install -y -qq --no-install-recommends curl \
    libx11-dev:armhf libxrandr-dev:armhf libxtst-dev:armhf libxt-dev:armhf >/dev/null
cd /tmp
curl -fsSLO https://go.dev/dl/$GO
echo "$GO_SHA  $GO" | sha256sum -c --quiet
tar -C /usr/local -xzf $GO
export PATH=/usr/local/go/bin:$PATH GOTOOLCHAIN=local
git clone -q --branch $TAG --depth 1 https://github.com/unrud/remote-touchpad.git
cd remote-touchpad
[ "$(git rev-parse --short=7 HEAD)" = "$COMMIT" ] || { echo "tag $TAG is not $COMMIT"; exit 1; }
CGO_ENABLED=1 CC=arm-linux-gnueabihf-gcc GOOS=linux GOARCH=arm GOARM=7 \
    go build -tags x11 -trimpath -ldflags "-s -w" -o /out/remote-touchpad .
cp COPYING /out/remote-touchpad.COPYING
cd /out && sha256sum remote-touchpad && ls -l remote-touchpad
arm-linux-gnueabihf-readelf -V remote-touchpad | grep -oE "GLIBC_[0-9.]+" | sort -Vu | tail -1
EOF
