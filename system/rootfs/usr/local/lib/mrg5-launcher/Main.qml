// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Roman Lut
// MRG5 TV launcher screen (checks/41, "TV launcher"); launcher.py loads it with the
// "backend" object. Laid out for 1920x1080. Energy: nothing animates by itself; the
// only timer is the clock, which fires once a minute and draws only when the text
// changes, and it stops while the window is hidden (a program in front).
import QtQuick 2.15
import QtQuick.Window 2.15
import QtGraphicalEffects 1.15

Window {
    id: win
    width: 1920
    height: 1080
    visible: true
    visibility: Window.FullScreen
    flags: Qt.FramelessWindowHint
    color: "#0b2a14"
    title: "MRG5 launcher"

    readonly property color accent: "#b9f23f"
    readonly property string face: "Quicksand"
    property string clock: ""
    property string message: ""

    function tick() {
        var d = new Date()
        clock = Qt.formatTime(d, "hh:mm")
        clockTimer.interval = (60 - d.getSeconds()) * 1000 + 100
        clockTimer.restart()
        backend.refreshStatus()
    }

    // One program at a time: while one is starting or running, keys and clicks on the
    // tiles do nothing and the selection stays on its tile.
    function launchCurrent() {
        if (backend.running)
            return
        message = ""
        if (list.currentIndex >= 0)
            backend.launch(list.currentIndex)
    }

    function comeBack() {
        pointer.shown = false
        win.showFullScreen()
        win.raise()
        win.requestActivate()
        list.forceActiveFocus()
        tick()
    }

    Timer { id: clockTimer; repeat: false; running: false; onTriggered: win.tick() }
    Component.onCompleted: {
        tick(); win.requestActivate(); list.forceActiveFocus()
        if (remote.firstStart)
            pairing.showNow()
    }
    onVisibleChanged: if (!visible) clockTimer.stop()

    Connections {
        target: backend
        function onAppWindowShown() { win.hide() }
        function onAppFinished(title, code) { win.comeBack() }
        function onAppFailed(title, reason) { win.message = title + " " + reason; win.comeBack() }
    }
    // the rear button held: pairing screen, only over the launcher itself
    Connections {
        target: resetButton
        function onHeld() {
            if (win.visible && !backend.running && !pairing.visible && !fader.busy)
                pairing.open()
        }
    }
    Connections {
        target: remote
        function onReady() { pairedPause.start() }
    }
    Timer { id: pairedPause; interval: 1500; onTriggered: pairing.finish() }

    // ---------- background ----------
    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#1f5a1c" }
            GradientStop { position: 1.0; color: "#0a2a12" }
        }
    }
    Image {
        anchors.fill: parent
        source: backend.background
        fillMode: Image.PreserveAspectCrop
        asynchronous: false
        cache: true
    }

    // ---------- top bar ----------
    Rectangle { x: 88; y: 64; width: 8; height: 52; radius: 4; color: win.accent }
    Text {
        x: 124; y: 60
        text: backend.title
        font.family: win.face; font.bold: true; font.pixelSize: 50
        color: "white"
        style: Text.Raised; styleColor: "#40000000"
    }

    Row {
        id: status
        anchors.right: parent.right; anchors.rightMargin: 80
        y: 62; height: 60
        spacing: 30

        component Sep: Rectangle { width: 2; height: 44; anchors.verticalCenter: parent.verticalCenter; color: "#66ffffff" }
        component Label: Text {
            anchors.verticalCenter: parent.verticalCenter
            font.family: win.face; font.bold: true; font.pixelSize: 30; color: "#e8ffffff"
        }
        component Icon: Image {
            anchors.verticalCenter: parent.verticalCenter
            width: 40; height: 40; sourceSize: Qt.size(80, 80); smooth: true
        }

        Label { text: win.clock; font.pixelSize: 36 }
        Sep {}
        Row {
            spacing: 14; anchors.verticalCenter: parent.verticalCenter
            visible: backend.ip !== ""
            Icon { source: "icons/network.svg" }
            Label { text: backend.ip }
        }
        Sep { visible: backend.ip !== "" }
        Row {
            spacing: 14; anchors.verticalCenter: parent.verticalCenter
            Icon { source: "icons/storage.svg" }
            Label { text: backend.freeSpace }
        }
        Sep {}
        Item {
            id: gear
            width: 60; height: 60
            anchors.verticalCenter: parent.verticalCenter
            Rectangle {
                anchors.fill: parent; radius: 30
                color: gear.activeFocus ? "#33ffffff" : "transparent"
                border.width: gear.activeFocus ? 3 : 0; border.color: win.accent
            }
            Image {
                anchors.centerIn: parent
                width: 42; height: 42; sourceSize: Qt.size(84, 84)
                source: "icons/settings.svg"
            }
            Keys.onDownPressed: list.forceActiveFocus()
            Keys.onReturnPressed: settings.open()
            Keys.onEnterPressed: settings.open()
            MouseArea { anchors.fill: parent; enabled: !backend.running; onClicked: settings.open() }
        }
    }

    // ---------- tiles ----------
    ListView {
        id: list
        x: 0; y: 330
        width: parent.width; height: 560
        orientation: ListView.Horizontal
        spacing: 30
        leftMargin: 130; rightMargin: 130
        topMargin: 30
        model: backend.tiles
        highlight: Item {}
        highlightRangeMode: ListView.ApplyRange
        preferredHighlightBegin: 130
        preferredHighlightEnd: width - 130
        highlightMoveDuration: 220
        highlightMoveVelocity: -1
        boundsBehavior: Flickable.StopAtBounds
        cacheBuffer: 2000
        keyNavigationWraps: false

        interactive: !backend.running
        Keys.onReturnPressed: win.launchCurrent()
        Keys.onEnterPressed: win.launchCurrent()
        Keys.onUpPressed: if (!backend.running) gear.forceActiveFocus()
        // arrows reach ListView's own navigation only when this does not accept them
        Keys.onPressed: {
            if (backend.running)
                event.accepted = true
            else
                win.message = ""
        }

        delegate: Item {
            id: tile
            width: 250; height: 380
            readonly property bool sel: ListView.isCurrentItem && (list.activeFocus || backend.running)
            z: sel ? 2 : 1
            scale: sel ? 1.1 : 1.0
            transformOrigin: Item.Center
            Behavior on scale { NumberAnimation { duration: 160; easing.type: Easing.OutCubic } }

            RectangularGlow {
                anchors.fill: body
                glowRadius: 26; spread: 0.2; cornerRadius: body.radius + glowRadius
                color: win.accent
                opacity: tile.sel ? 0.6 : 0
                visible: opacity > 0
                Behavior on opacity { NumberAnimation { duration: 160 } }
            }

            Rectangle {
                id: body
                anchors.fill: parent
                radius: 28
                gradient: Gradient {
                    GradientStop { position: 0.0; color: Qt.lighter(modelData.color, 1.45) }
                    GradientStop { position: 0.45; color: modelData.color }
                    GradientStop { position: 1.0; color: Qt.darker(modelData.color, 2.2) }
                }
                border.width: tile.sel ? 5 : 2
                border.color: tile.sel ? "#dcff6a" : "#30ffffff"

                // soft shade behind the icon, as on the concept
                Rectangle {
                    width: 230; height: 230; radius: 115
                    anchors.horizontalCenter: parent.horizontalCenter
                    y: 34
                    color: "#26000000"
                }
                Image {
                    source: modelData.icon
                    width: 150 * modelData.iconScale; height: width
                    anchors.horizontalCenter: parent.horizontalCenter
                    y: 150 - height / 2
                    sourceSize: Qt.size(300, 300)
                    fillMode: Image.PreserveAspectFit
                    smooth: true; mipmap: true
                }
                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    anchors.bottom: parent.bottom; anchors.bottomMargin: 40
                    width: parent.width - 24
                    horizontalAlignment: Text.AlignHCenter
                    elide: Text.ElideRight
                    text: modelData.title
                    font.family: win.face; font.bold: true; font.pixelSize: 32
                    color: "white"
                    style: Text.Raised; styleColor: "#50000000"
                }
            }

            // reflection on the "floor": the lower part of the tile, mirrored and faded
            ShaderEffectSource {
                id: lower
                sourceItem: body
                sourceRect: Qt.rect(0, body.height - 110, body.width, 110)
                width: body.width; height: 110
                visible: false
            }
            LinearGradient {
                id: fade
                width: body.width; height: 110
                visible: false
                start: Qt.point(0, 0); end: Qt.point(0, 110)
                gradient: Gradient {
                    GradientStop { position: 0.0; color: "#00000000" }
                    GradientStop { position: 1.0; color: "#ff000000" }
                }
            }
            OpacityMask {
                width: body.width; height: 110
                y: body.height + 10
                source: lower; maskSource: fade
                opacity: 0.16
                transform: Scale { origin.y: 55; yScale: -1 }
            }

            MouseArea {
                anchors.fill: body
                enabled: !backend.running
                onClicked: { list.currentIndex = index; list.forceActiveFocus(); win.launchCurrent() }
            }
        }
    }

    // ---------- side arrows (shown while the row can scroll that way) ----------
    component Arrow: Rectangle {
        property bool back: false
        width: 72; height: 72; radius: 36
        y: list.y + list.topMargin + 190 - 36
        color: "#59000000"
        border.width: 2; border.color: "#33ffffff"
        Image {
            anchors.centerIn: parent
            width: 36; height: 36; sourceSize: Qt.size(72, 72)
            source: "icons/chevron.svg"
            rotation: parent.back ? 180 : 0
        }
        MouseArea {
            anchors.fill: parent
            enabled: !backend.running
            onClicked: {
                list.forceActiveFocus()
                if (parent.back) list.decrementCurrentIndex(); else list.incrementCurrentIndex()
            }
        }
    }
    Arrow { back: true; x: 36; visible: list.contentX > list.originX - list.leftMargin + 2 }
    Arrow { back: false; x: parent.width - 36 - width
            visible: list.contentX + list.width < list.originX + list.contentWidth + list.rightMargin - 2 }

    // ---------- "starting" / error notice ----------
    Rectangle {
        visible: backend.running || win.message !== ""
        anchors.horizontalCenter: parent.horizontalCenter
        y: 930
        width: note.implicitWidth + 80; height: 76; radius: 38
        color: "#99000000"
        border.width: 2; border.color: "#40ffffff"
        Text {
            id: note
            anchors.centerIn: parent
            text: win.message !== "" ? win.message
                  : "Starting " + backend.startedTitle + " …"
            font.family: win.face; font.bold: true; font.pixelSize: 32; color: "white"
        }
    }

    // ---------- remote pairing screen ----------
    // Shown at the first start (no flag file yet) and when the rear button is held.
    // pair-remote.py searches for the remote in pairing mode and pairs it; once it is
    // paired, or Esc is pressed (keyboard, or a paired remote's Back), the screen fades
    // to black and the launcher fades in, and the flag is written.
    Item {
        id: pairing
        anchors.fill: parent
        z: 900
        visible: false
        property bool closing: false

        function showNow() {                          // first start: from black
            fader.opacity = 1
            fader.run(function() { pairing.enter() })
        }
        function open() {                             // over the launcher
            fader.run(function() { pairing.enter() })
        }
        function enter() {
            settings.visible = false
            if (btdlg.visible) { btpair.stop(); btdlg.visible = false }
            win.message = ""
            closing = false
            visible = true
            forceActiveFocus()
            remote.start()
        }
        function finish() {                           // paired, or skipped
            if (closing)
                return
            closing = true
            pairedPause.stop()
            remote.markDone()
            fader.run(function() {
                remote.stop()
                pairing.visible = false
                list.forceActiveFocus()
                win.tick()
            })
        }

        Keys.onPressed: {
            event.accepted = true
            if (event.key === Qt.Key_Escape)
                finish()
        }
        MouseArea { anchors.fill: parent }            // clicks do not reach the tiles

        Image {
            anchors.fill: parent
            source: "images/pair-remote.png"
            fillMode: Image.PreserveAspectCrop
            sourceSize.width: 1920
            smooth: true
        }

        // progress, under the picture's instructions
        Rectangle {
            x: 838; y: 690
            width: stateText.implicitWidth + 100; height: 76; radius: 38
            color: "#80000000"
            border.width: 2
            border.color: remote.state === "ready" ? win.accent : "#40ffffff"
            Rectangle {
                id: dot
                x: 32; anchors.verticalCenter: parent.verticalCenter
                width: 20; height: 20; radius: 10
                color: remote.state === "failed" || remote.state === "error" ? "#ff6a5a" : win.accent
                // pulses only while this screen waits for the remote
                SequentialAnimation on opacity {
                    running: pairing.visible && remote.state !== "ready"
                    loops: Animation.Infinite
                    NumberAnimation { to: 0.25; duration: 700; easing.type: Easing.InOutSine }
                    NumberAnimation { to: 1.0; duration: 700; easing.type: Easing.InOutSine }
                    onStopped: dot.opacity = 1
                }
            }
            Text {
                id: stateText
                x: 68; anchors.verticalCenter: parent.verticalCenter
                font.family: win.face; font.bold: true; font.pixelSize: 32; color: "white"
                text: {
                    switch (remote.state) {
                    case "found": return "Remote found: " + remote.detail
                    case "removed": return "Remote found, renewing its pairing …"
                    case "pairing": return "Pairing with " + remote.detail + " …"
                    case "paired": return "Paired, connecting …"
                    case "ready": return "Remote paired"
                    case "failed": return "Pairing failed - hold the button again"
                    case "error": return "Bluetooth is not ready, trying again …"
                    default: return "Looking for the remote …"
                    }
                }
            }
        }

        Text {
            x: 838; y: 990
            text: "Esc on the keyboard: skip"
            font.family: win.face; font.bold: true; font.pixelSize: 28; color: "#b3ffffff"
        }
    }

    // ---------- fade through black: fade out, swap what is shown, fade in ----------
    Rectangle {
        id: fader
        anchors.fill: parent
        z: 950
        color: "black"
        opacity: 0
        visible: opacity > 0
        readonly property bool busy: fadeAnim.running
        property var middle: null
        function run(f) { middle = f; fadeAnim.restart() }
        MouseArea { anchors.fill: parent; enabled: fader.busy }
        SequentialAnimation {
            id: fadeAnim
            NumberAnimation { target: fader; property: "opacity"; to: 1; duration: 600; easing.type: Easing.InOutQuad }
            ScriptAction { script: { var f = fader.middle; fader.middle = null; if (f) f() } }
            PauseAnimation { duration: 250 }
            NumberAnimation { target: fader; property: "opacity"; to: 0; duration: 700; easing.type: Easing.InOutQuad }
        }
    }

    // ---------- mouse pointer: hidden at start, and 5 s after the last movement ----------
    // On top of everything, takes no buttons (clicks reach the tiles below) and only
    // watches movement. Changing the pointer shape redraws nothing in the scene.
    MouseArea {
        id: pointer
        anchors.fill: parent
        z: 1000
        acceptedButtons: Qt.NoButton
        hoverEnabled: true
        property bool shown: false
        cursorShape: shown ? Qt.ArrowCursor : Qt.BlankCursor
        onPositionChanged: { shown = true; pointerTimer.restart() }
        Timer { id: pointerTimer; interval: 5000; onTriggered: pointer.shown = false }
    }

    // ---------- settings ----------
    // Buttons: "Pair Bluetooth Device", "Switch standby CPU frequency", "Restart the box",
    // "Close". There is no storage switch (owner, 2026-10-01; launcher.py, "data storage").
    Rectangle {
        id: settings
        anchors.fill: parent
        color: "#b3000000"
        visible: false
        property int sel: 0
        readonly property var actions: {
            var a = []
            a.push({ label: "Pair Bluetooth Device", act: "bt" })
            a.push({ label: "Switch standby CPU frequency", act: "cpu" })
            a.push({ label: "Restart the box", act: "reboot" })
            a.push({ label: "Close", act: "close" })
            return a
        }
        function open() { backend.refreshSettings(); sel = 0; visible = true; forceActiveFocus() }
        function close() { visible = false; list.forceActiveFocus() }
        function activate() {
            var act = actions[Math.min(sel, actions.length - 1)].act
            if (act === "bt") { visible = false; btdlg.open() }
            else if (act === "cpu") backend.toggleStandbyCpu()
            else if (act === "reboot") backend.reboot()
            else close()
        }
        onActionsChanged: sel = Math.min(sel, actions.length - 1)

        Keys.onUpPressed: sel = Math.max(0, sel - 1)
        Keys.onDownPressed: sel = Math.min(actions.length - 1, sel + 1)
        Keys.onReturnPressed: activate()
        Keys.onEnterPressed: activate()
        Keys.onEscapePressed: close()
        MouseArea { anchors.fill: parent; onClicked: settings.close() }

        Rectangle {
            anchors.centerIn: parent
            width: Math.max(720, settingsCol.implicitWidth + 120); height: settingsCol.implicitHeight + 90; radius: 32
            color: "#e6142a1a"
            border.width: 2; border.color: "#40ffffff"
            MouseArea { anchors.fill: parent }

            Column {
                id: settingsCol
                anchors.centerIn: parent
                spacing: 22
                // the title and the texts, and to their right, from the top, the phone remote's
                // QR code (launcher.py, phone_remote_qr; checks/41, "Phone remote") when there is one
                Row {
                    id: settingsTop
                    spacing: 56
                    Column {
                        spacing: 22
                        Text { text: "Settings"; font.family: win.face; font.bold: true; font.pixelSize: 44; color: "white" }
                        Text {
                            text: "Address: " + (backend.ip || "none")
                                  + "\nFree space: " + backend.freeSpace
                                  + (backend.storageName ? " (" + backend.storageName + ")" : "")
                                  + "\nFree RAM: " + backend.freeRam
                                  + "\nStandby CPU frequency: " + (backend.standbyCpuLow ? "Low" : "Normal")
                            font.family: win.face; font.bold: true; font.pixelSize: 28; color: "#ccffffff"
                            lineHeight: 1.2
                        }
                    }
                    Column {
                        visible: backend.phoneRemoteQr !== ""
                        spacing: 12
                        Rectangle {
                            anchors.horizontalCenter: parent.horizontalCenter
                            width: qr.implicitWidth + 16; height: qr.implicitHeight + 16
                            radius: 12; color: "white"
                            // drawn 1:1 (7 px per module), so the camera sees sharp squares
                            Image { id: qr; anchors.centerIn: parent; source: backend.phoneRemoteQr; cache: false; smooth: false }
                        }
                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
                            horizontalAlignment: Text.AlignHCenter
                            text: "Scan with your phone:\ntouchpad and keyboard"
                            font.family: win.face; font.bold: true; font.pixelSize: 22; color: "#ccffffff"
                        }
                    }
                }
                Repeater {
                    model: settings.actions
                    Rectangle {
                        // the full width of the texts and the QR code above
                        width: Math.max(560, settingsTop.width); height: 72; radius: 36
                        color: settings.sel === index ? "#33ffffff" : "#14ffffff"
                        border.width: settings.sel === index ? 4 : 0; border.color: win.accent
                        Text {
                            anchors.centerIn: parent; text: modelData.label
                            font.family: win.face; font.bold: true; font.pixelSize: 32; color: "white"
                        }
                        MouseArea { anchors.fill: parent; onClicked: { settings.sel = index; settings.activate() } }
                    }
                }
            }
        }
    }

    // ---------- settings -> "Pair Bluetooth Device" ----------
    // A 10 s search (pair-device.py scan), then the devices found; OK pairs the selected one
    // (pair, trust, connect). The last row searches again. Back returns to the settings.
    Rectangle {
        id: btdlg
        anchors.fill: parent
        color: "#b3000000"
        visible: false
        property int sel: 0
        readonly property bool busy: btpair.state === "searching" || btpair.state === "pairing"
        readonly property int rows: btpair.devices.length + 1      // + "Search again"

        function open() { sel = 0; visible = true; forceActiveFocus(); btpair.search() }
        function close() { btpair.stop(); visible = false; settings.open() }
        function move(d) {
            if (busy) return
            sel = Math.max(0, Math.min(rows - 1, sel + d))
            devList.positionViewAtIndex(sel, ListView.Contain)
        }
        function activate() {
            if (busy) return
            if (sel >= btpair.devices.length) { sel = 0; btpair.search() }
            else btpair.pair(btpair.devices[sel].mac)
        }
        onRowsChanged: sel = Math.min(sel, rows - 1)

        Keys.onUpPressed: move(-1)
        Keys.onDownPressed: move(1)
        Keys.onReturnPressed: activate()
        Keys.onEnterPressed: activate()
        Keys.onEscapePressed: close()
        MouseArea { anchors.fill: parent; onClicked: btdlg.close() }

        Rectangle {
            anchors.centerIn: parent
            width: 1060; height: 860; radius: 32
            color: "#e6142a1a"
            border.width: 2; border.color: "#40ffffff"
            MouseArea { anchors.fill: parent }

            Text {
                x: 70; y: 50
                text: "Pair Bluetooth Device"
                font.family: win.face; font.bold: true; font.pixelSize: 44; color: "white"
            }
            Text {
                x: 70; y: 122; width: parent.width - 140
                elide: Text.ElideRight
                font.family: win.face; font.bold: true; font.pixelSize: 30
                color: btpair.state === "failed" ? "#ff8a7a"
                       : btpair.state === "paired" ? win.accent : "#ccffffff"
                text: {
                    switch (btpair.state) {
                    case "searching": return "Searching … " + btpair.secondsLeft + " s"
                    case "list": return btpair.devices.length ? "Choose a device and press OK"
                                                              : "No devices found"
                    default: return btpair.detail
                    }
                }
            }

            ListView {
                id: devList
                x: 70; y: 190
                width: parent.width - 140; height: 7 * 84
                clip: true
                spacing: 12
                interactive: false
                model: btdlg.rows
                delegate: Rectangle {
                    readonly property bool more: index >= btpair.devices.length
                    readonly property var d: more ? null : btpair.devices[index]
                    readonly property bool cur: btdlg.sel === index && !btdlg.busy
                    width: devList.width; height: 72; radius: 36
                    // "Search again" is an action, not a device: accent colour, centred
                    color: more ? (cur ? win.accent : "#7aa82a") : (cur ? "#33ffffff" : "#14ffffff")
                    border.width: cur ? 4 : 0; border.color: more ? "white" : win.accent
                    opacity: btdlg.busy && !more ? 0.6 : 1
                    visible: !more || btpair.state !== "searching"
                    Text {
                        x: more ? (parent.width - width) / 2 : 40
                        anchors.verticalCenter: parent.verticalCenter
                        width: more ? implicitWidth : parent.width - 80 - tag.implicitWidth
                        elide: Text.ElideRight
                        text: more ? "Search again" : d.name
                        font.family: win.face; font.bold: true; font.pixelSize: 32
                        color: more ? "#0b2a14" : "white"
                    }
                    Text {
                        id: tag
                        anchors.right: parent.right; anchors.rightMargin: 40
                        anchors.verticalCenter: parent.verticalCenter
                        text: more ? "" : [d.kind, d.paired ? "paired" : ""].filter(Boolean).join(" · ")
                        font.family: win.face; font.bold: true; font.pixelSize: 26
                        color: !more && d.paired ? win.accent : "#99ffffff"
                    }
                    MouseArea {
                        anchors.fill: parent
                        onClicked: { if (!btdlg.busy) { btdlg.sel = index; btdlg.activate() } }
                    }
                }
            }

            Text {
                x: 70; y: parent.height - 80
                text: "Put the device in pairing mode first (DualShock 4: hold Share + PS)   ·   Back: close"
                font.family: win.face; font.bold: true; font.pixelSize: 24; color: "#99ffffff"
            }
        }
    }
}
