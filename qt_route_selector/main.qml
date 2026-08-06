import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import OfflineMap 1.0

ApplicationWindow {
    id: root
    visible: true
    width: 1280
    height: 800
    minimumWidth: 900
    minimumHeight: 600
    title: "GPS-Routen- und Geschwindigkeitsprofil – Offline"

    property bool startValid: false
    property bool targetValid: false
    property var routeSummary: ({})
    property var mapSummary: ({})

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        ToolBar {
            Layout.fillWidth: true

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 8
                anchors.rightMargin: 8

                Button {
                    text: "Straßendaten wählen"
                    enabled: !routeSelector.busy
                    onClicked: routeSelector.chooseRoadData()
                }

                Button {
                    text: "Kartenausschnitt laden"
                    enabled: !routeSelector.busy && routeSelector.roadsFile.length > 0
                    onClicked: routeSelector.loadRoadMap(offlineMap.visibleBounds())
                }

                Button {
                    text: "Route berechnen"
                    enabled: !routeSelector.busy && root.startValid && root.targetValid
                    highlighted: true
                    onClicked: routeSelector.calculateRoute()
                }

                Button {
                    text: "Route einpassen"
                    enabled: !routeSelector.busy
                        && root.routeSummary.route_points !== undefined
                        && root.routeSummary.route_points > 1
                    onClicked: offlineMap.fitRoute()
                }

                Button {
                    text: "Zurücksetzen"
                    enabled: !routeSelector.busy
                    onClicked: routeSelector.resetSelection()
                }

                Item { Layout.fillWidth: true }

                BusyIndicator {
                    running: routeSelector.busy
                    visible: running
                    implicitWidth: 30
                    implicitHeight: 30
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            Item {
                Layout.fillWidth: true
                Layout.fillHeight: true

                OfflineMapItem {
                    id: offlineMap
                    anchors.fill: parent
                    centerLatitude: 48.743
                    centerLongitude: 9.320
                    zoomLevel: 12

                    onCoordinateClicked: (latitude, longitude) => {
                        if (!routeSelector.busy) {
                            routeSelector.selectPoint(latitude, longitude)
                        }
                    }
                }

                Rectangle {
                    anchors.left: parent.left
                    anchors.top: parent.top
                    anchors.margins: 12
                    width: instructionLabel.implicitWidth + 24
                    height: instructionLabel.implicitHeight + 16
                    radius: 5
                    color: "#e8ffffff"
                    border.color: "#bbbbbb"

                    Label {
                        id: instructionLabel
                        anchors.centerIn: parent
                        text: routeSelector.roadsFile.length === 0
                            ? "1. Lokale Straßendaten wählen"
                            : (!root.startValid
                                ? "2. Startpunkt anklicken"
                                : (!root.targetValid
                                    ? "3. Zielpunkt anklicken"
                                    : "4. Route berechnen"))
                    }
                }

                Column {
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.margins: 12
                    spacing: 6

                    Button {
                        width: 38
                        height: 38
                        text: "+"
                        font.pixelSize: 20
                        onClicked: offlineMap.zoomLevel = offlineMap.zoomLevel + 0.5
                    }

                    Button {
                        width: 38
                        height: 38
                        text: "−"
                        font.pixelSize: 20
                        onClicked: offlineMap.zoomLevel = offlineMap.zoomLevel - 0.5
                    }
                }

                Rectangle {
                    anchors.left: parent.left
                    anchors.bottom: parent.bottom
                    anchors.margins: 12
                    width: interactionLabel.implicitWidth + 20
                    height: interactionLabel.implicitHeight + 12
                    radius: 4
                    color: "#dfffffff"
                    border.color: "#cccccc"

                    Label {
                        id: interactionLabel
                        anchors.centerIn: parent
                        text: "Ziehen: Karte verschieben · Mausrad: zoomen · Klick: Punkt wählen"
                        color: "#4b5055"
                    }
                }
            }

            Pane {
                Layout.preferredWidth: 350
                Layout.fillHeight: true

                ScrollView {
                    anchors.fill: parent
                    contentWidth: availableWidth

                    ColumnLayout {
                        width: parent.width
                        spacing: 12

                        Label {
                            text: "Lokale Routingdaten"
                            font.bold: true
                            font.pixelSize: 17
                        }

                        Label {
                            Layout.fillWidth: true
                            text: routeSelector.roadsFile.length > 0
                                ? routeSelector.roadsFile
                                : "Noch keine lokale Straßendatei gewählt"
                            wrapMode: Text.WrapAnywhere
                            color: routeSelector.roadsFile.length > 0
                                ? palette.text
                                : palette.placeholderText
                        }

                        GridLayout {
                            columns: 2
                            columnSpacing: 14
                            rowSpacing: 7

                            Label { text: "Kartenlinien:" }
                            Label {
                                text: root.mapSummary.display_lines === undefined
                                    ? "–"
                                    : root.mapSummary.display_lines
                            }

                            Label { text: "Kartenpunkte:" }
                            Label {
                                text: root.mapSummary.display_vertices === undefined
                                    ? "–"
                                    : root.mapSummary.display_vertices
                            }

                            Label { text: "Quell-Features:" }
                            Label {
                                text: root.mapSummary.source_features === undefined
                                    ? "–"
                                    : root.mapSummary.source_features
                            }

                            Label { text: "Anzeige begrenzt:" }
                            Label {
                                text: root.mapSummary.truncated === undefined
                                    ? "–"
                                    : (root.mapSummary.truncated ? "Ja" : "Nein")
                            }
                        }

                        MenuSeparator { Layout.fillWidth: true }

                        Label {
                            text: "Route"
                            font.bold: true
                            font.pixelSize: 17
                        }

                        GridLayout {
                            columns: 2
                            columnSpacing: 14
                            rowSpacing: 8

                            Label { text: "Entfernung:" }
                            Label {
                                text: root.routeSummary.distance_km === undefined
                                    ? "–"
                                    : Number(root.routeSummary.distance_km).toFixed(2) + " km"
                                font.bold: true
                            }

                            Label { text: "Fahrzeit (OSM):" }
                            Label {
                                text: root.routeSummary.estimated_minutes === undefined
                                    ? "–"
                                    : Number(root.routeSummary.estimated_minutes).toFixed(1) + " min"
                            }

                            Label { text: "Straßensegmente:" }
                            Label {
                                text: root.routeSummary.road_segments === undefined
                                    ? "–"
                                    : root.routeSummary.road_segments
                            }

                            Label { text: "Ampeln:" }
                            Label {
                                text: root.routeSummary.traffic_signals === undefined
                                    ? "–"
                                    : root.routeSummary.traffic_signals
                            }

                            Label { text: "Geladene Features:" }
                            Label {
                                text: root.routeSummary.loaded_features === undefined
                                    ? "–"
                                    : root.routeSummary.loaded_features
                            }

                            Label { text: "Graphknoten:" }
                            Label {
                                text: root.routeSummary.graph_nodes === undefined
                                    ? "–"
                                    : root.routeSummary.graph_nodes
                            }

                            Label { text: "Start-Snap:" }
                            Label {
                                text: root.routeSummary.start_snap_m === undefined
                                    ? "–"
                                    : Math.round(root.routeSummary.start_snap_m) + " m"
                            }

                            Label { text: "Ziel-Snap:" }
                            Label {
                                text: root.routeSummary.target_snap_m === undefined
                                    ? "–"
                                    : Math.round(root.routeSummary.target_snap_m) + " m"
                            }
                        }

                        MenuSeparator { Layout.fillWidth: true }

                        Label {
                            Layout.fillWidth: true
                            text: "Die Karte, das Routing und die OSM-Auswertung arbeiten vollständig lokal. "
                                + "Nach Verschieben oder starkem Zoomen den sichtbaren Kartenausschnitt "
                                + "erneut laden. Die Route wird zusätzlich als route_result.json gespeichert."
                            wrapMode: Text.WordWrap
                            color: palette.placeholderText
                        }
                    }
                }
            }
        }

        Frame {
            Layout.fillWidth: true
            padding: 8

            Label {
                id: statusLabel
                width: parent.width
                text: "Lokale Straßendatei wählen. Es wird keine Internetverbindung verwendet."
                elide: Text.ElideRight
            }
        }
    }

    Timer {
        id: initialLoadTimer
        interval: 350
        repeat: false
        onTriggered: {
            if (routeSelector.roadsFile.length > 0 && !routeSelector.busy) {
                routeSelector.loadRoadMap(offlineMap.visibleBounds())
            }
        }
    }

    Component.onCompleted: {
        if (routeSelector.roadsFile.length > 0) {
            initialLoadTimer.start()
        }
    }

    Connections {
        target: routeSelector

        function onStatusChanged(message) {
            statusLabel.text = message
        }

        function onRoadsFileChanged() {
            offlineMap.clearRoads()
            root.mapSummary = ({})
            initialLoadTimer.restart()
        }

        function onMapRoadsChanged(features) {
            offlineMap.setRoads(features)
        }

        function onMapSummaryChanged(summary) {
            root.mapSummary = summary
        }

        function onSelectionChanged(data) {
            root.startValid = data.points.length > 0
            root.targetValid = data.points.length > 1
            offlineMap.setSelection(data)
        }

        function onRouteChanged(points) {
            offlineMap.setRoute(points)
            if (points.length > 1) {
                offlineMap.fitRoute()
            }
        }

        function onSignalsChanged(points) {
            offlineMap.setSignals(points)
        }

        function onSummaryChanged(summary) {
            root.routeSummary = summary
        }
    }
}
