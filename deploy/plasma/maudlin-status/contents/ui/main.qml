// The desktop status card (Oct 11): what the machine is doing for bignews.day, from app/desk.py --json every INTERVAL
// ms. A translucent glass card over the wallpaper, no Plasma background: a large line with a dot in the card's own light
// colour (it breathes when the light does), meters for the GPU, a few quiet rows, what the work queue says is running,
// and the lights' key. Install: kpackagetool6 -t Plasma/Applet -i deploy/plasma/maudlin-status (-u to update), then
// restart plasmashell to load the new version.
import QtQuick
import QtQuick.Layouts
import QtQuick.Effects
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.plasma5support as P5Support
import org.kde.kirigami as Kirigami

PlasmoidItem {
    id: root
    readonly property int interval: 15000
    // the production checkout, else the working one (a new app/desk.py reaches production at the next hourly run)
    readonly property string command: "cd /home/mas/maudlin-prod && .venv/bin/python -m app.desk --json 2>/dev/null || (cd /home/mas/Repos/maudlin2 && .venv/bin/python -m app.desk --json)"
    property var d: ({})
    property string error: ""

    Plasmoid.backgroundHints: PlasmaCore.Types.NoBackground
    preferredRepresentation: fullRepresentation

    readonly property color ink: "#ffffff"
    readonly property color quiet: Qt.rgba(1, 1, 1, 0.74)
    readonly property color faint: Qt.rgba(1, 1, 1, 0.62)
    readonly property color lightColor: d.look ? d.look.color : "#666666"

    P5Support.DataSource {
        id: runner
        engine: "executable"
        connectedSources: []
        onNewData: (source, data) => {
            try {
                root.d = JSON.parse(data["stdout"])
                root.error = ""
            } catch (e) {
                root.error = (data["stderr"] || "app/desk.py said nothing").split("\n").slice(-2).join(" ")
            }
            disconnectSource(source)
        }
    }

    Timer {
        interval: root.interval
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: runner.connectSource(root.command)
    }

    readonly property int meterWidth: 168  // the four meters alike (the person: "not the same widths which is weird")
    readonly property int textCap: 380  // a long line elides here rather than widening its tile

    component Meter: ColumnLayout {
        property string label
        property string value
        property real fraction
        property color tint: root.ink
        spacing: 4
        Layout.preferredWidth: root.meterWidth
        RowLayout {
            Layout.fillWidth: true
            Text { text: label; color: root.quiet; font.pixelSize: 12; font.letterSpacing: 0.6; font.capitalization: Font.AllUppercase }
            Item { Layout.fillWidth: true }
            Text { text: value; color: root.ink; font.pixelSize: 13; font.features: { "tnum": 1 } }
        }
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: 4
            radius: 2
            color: Qt.rgba(1, 1, 1, 0.14)
            Rectangle {
                width: parent.width * Math.max(0, Math.min(1, fraction))
                height: parent.height
                radius: 2
                color: tint
                Behavior on width { NumberAnimation { duration: 600; easing.type: Easing.OutCubic } }
            }
        }
    }

    // One section's own dark background, as wide as what's in it (the person, Oct 11: no glass sheet, each part its
    // own darker tile, none wider than it needs)
    component Tile: Rectangle {
        default property alias content: inner.data
        implicitWidth: inner.implicitWidth + 30
        implicitHeight: inner.implicitHeight + 24
        radius: 12
        color: Qt.rgba(0.04, 0.05, 0.05, 0.80)
        ColumnLayout {
            id: inner
            x: 15
            y: 12
            spacing: 6
        }
    }

    component Row2: RowLayout {
        property string name
        property string value
        spacing: 12
        Text { text: name; color: root.quiet; font.pixelSize: 13; Layout.preferredWidth: 92 }
        Text { text: value; color: root.ink; font.pixelSize: 13; Layout.maximumWidth: root.textCap; elide: Text.ElideRight; font.features: { "tnum": 1 } }
    }

    fullRepresentation: Item {
        Layout.preferredWidth: card.implicitWidth
        Layout.preferredHeight: card.implicitHeight
        Layout.minimumWidth: 300

        ColumnLayout {
            id: card
            anchors { left: parent.left; top: parent.top }
            spacing: 8

            // What the machine is doing, in the light's own colour
            Tile {
                RowLayout {
                    spacing: 12
                    Item {
                        implicitWidth: 16
                        implicitHeight: 16
                        Rectangle {
                            id: halo
                            anchors.centerIn: parent
                            width: 16; height: 16; radius: 8
                            color: root.lightColor
                            opacity: 0.35
                            scale: 1.6
                        }
                        Rectangle {
                            anchors.centerIn: parent
                            width: 10; height: 10; radius: 5
                            color: root.d.look && root.d.look.brightness === 0 ? "transparent" : root.lightColor
                            border.color: root.lightColor
                            border.width: 1
                        }
                        SequentialAnimation {
                            running: root.d.look ? root.d.look.effect === "breathing" || root.d.look.effect === "flowing" : false
                            loops: Animation.Infinite
                            NumberAnimation { target: halo; property: "opacity"; from: 0.12; to: 0.55; duration: 2400; easing.type: Easing.InOutSine }
                            NumberAnimation { target: halo; property: "opacity"; from: 0.55; to: 0.12; duration: 2400; easing.type: Easing.InOutSine }
                        }
                    }
                    ColumnLayout {
                        spacing: 1
                        Text {
                            text: root.error ? "Can't read the machine" : (root.d.look ? root.d.look.title : "Reading the machine…")
                            color: root.ink
                            font.pixelSize: 20
                            font.weight: Font.DemiBold
                        }
                        Text {
                            text: root.error ? root.error : (root.d.gpu ? (root.d.gpu.models.length ? root.d.gpu.models.join(" · ") : "no model loaded") + "  ·  " + root.d.time : "")
                            color: root.quiet
                            font.pixelSize: 13
                            Layout.maximumWidth: root.textCap
                            elide: Text.ElideRight
                        }
                    }
                }
            }

            // The GPU
            Tile {
                visible: !!root.d.gpu
                GridLayout {
                    columns: 2
                    columnSpacing: 22
                    rowSpacing: 10
                    Meter {
                        label: "Load"
                        value: root.d.gpu ? Math.round(root.d.gpu.util) + "%" : ""
                        fraction: root.d.gpu ? root.d.gpu.util / 100 : 0
                        tint: root.lightColor
                    }
                    Meter {
                        label: "Heat"
                        value: root.d.gpu ? Math.round(root.d.gpu.temp) + "°C" : ""
                        fraction: root.d.gpu ? (root.d.gpu.temp - 30) / 63 : 0
                        tint: root.d.gpu && root.d.gpu.temp >= 85 ? "#ff7a3d" : Qt.rgba(1, 1, 1, 0.75)
                    }
                    Meter {
                        label: "Memory"
                        value: root.d.gpu ? root.d.gpu.mem + " / " + root.d.gpu.mem_total + " GB" : ""
                        fraction: root.d.gpu ? root.d.gpu.mem / root.d.gpu.mem_total : 0
                        tint: Qt.rgba(1, 1, 1, 0.75)
                    }
                    Meter {
                        label: "Power"
                        value: root.d.gpu ? root.d.gpu.power + " W" : ""
                        fraction: root.d.gpu ? root.d.gpu.power / 370 : 0
                        tint: Qt.rgba(1, 1, 1, 0.75)
                    }
                }
            }

            Tile {
                ColumnLayout {
                    spacing: 5
                    Repeater {
                        model: root.d.rows || []
                        delegate: Row2 { name: modelData.name; value: modelData.value }
                    }
                    Row2 { name: "GPU lease"; value: root.d.lease ? root.d.lease : "free" }
                }
            }

            Tile {
                visible: (root.d.running || []).length > 0
                ColumnLayout {
                    spacing: 4
                    Text { text: "Running now"; color: root.quiet; font.pixelSize: 12; font.letterSpacing: 0.6; font.capitalization: Font.AllUppercase }
                    Repeater {
                        model: root.d.running || []
                        delegate: Text {
                            text: "–  " + modelData
                            color: root.ink
                            font.pixelSize: 13
                            Layout.maximumWidth: root.textCap
                            elide: Text.ElideRight
                        }
                    }
                }
            }

            // The lights' key, and the machine
            Tile {
                RowLayout {
                    spacing: 12
                    Repeater {
                        model: [["#00beaa", "worker"], ["#8c3cff", "experiment"], ["#ff8c00", "hourly"],
                                ["#2850c8", "idle"], ["#ff0000", "failed/hot"], ["#780c00", "night"]]
                        delegate: RowLayout {
                            spacing: 5
                            Rectangle { implicitWidth: 7; implicitHeight: 7; radius: 3.5; color: modelData[0] }
                            Text { text: modelData[1]; color: root.faint; font.pixelSize: 12 }
                        }
                    }
                }
                Text { text: root.d.machine || ""; color: root.faint; font.pixelSize: 12 }
            }
        }
    }
}
