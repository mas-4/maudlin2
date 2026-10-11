// The desktop status panel (Oct 11): runs app/desk.py from the production checkout every INTERVAL ms and shows its
// text. Install: kpackagetool6 -t Plasma/Applet -i deploy/plasma/maudlin-status (-u to update), then add "Maudlin
// status" to the desktop.
import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.components as PlasmaComponents
import org.kde.plasma.plasma5support as P5Support
import org.kde.kirigami as Kirigami

PlasmoidItem {
    id: root
    readonly property int interval: 15000
    readonly property string command: "cd /home/mas/maudlin-prod && .venv/bin/python -m app.desk"
    property string panel: "Reading the machine…"

    preferredRepresentation: fullRepresentation

    P5Support.DataSource {
        id: runner
        engine: "executable"
        connectedSources: []
        onNewData: (source, data) => {
            const out = (data["stdout"] || "").trim()
            root.panel = out.length ? out : ("app/desk.py said nothing\n" + (data["stderr"] || ""))
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

    fullRepresentation: Item {
        Layout.preferredWidth: Kirigami.Units.gridUnit * 34
        Layout.preferredHeight: text.implicitHeight + Kirigami.Units.largeSpacing * 2
        Layout.minimumWidth: Kirigami.Units.gridUnit * 20

        PlasmaComponents.Label {
            id: text
            anchors.fill: parent
            anchors.margins: Kirigami.Units.largeSpacing
            text: root.panel
            textFormat: Text.PlainText
            font.family: "monospace"
            wrapMode: Text.NoWrap
            elide: Text.ElideRight
        }
    }
}
