import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtLocation
import QtPositioning

ApplicationWindow {
    id: root
    visible: true
    width: 1280
    height: 800
    minimumWidth: 900
    minimumHeight: 600
    title: "GPS-Routen- und Geschwindigkeitsprofil"

    property bool startValid: false
    property bool targetValid: false
    property var selectedRegion: null
    property var routeSummary: ({})

    Plugin {
        id: osmPlugin
        name: "osm"

        // Do not let Qt dynamically select a third-party provider such as
        // Thunderforest. The custom map below uses the public OSM standard
        // tiles and therefore needs no API key.
        PluginParameter {
            name: "osm.mapping.providersrepository.disabled"
            value: true
        }
        PluginParameter {
            name: "osm.mapping.custom.host"
            value: "https://tile.openstreetmap.org/"
        }
        PluginParameter {
            name: "osm.mapping.custom.datacopyright"
            value: "© OpenStreetMap contributors"
        }
        PluginParameter {
            name: "osm.mapping.prefetching_style"
            value: "NoPrefetching"
        }
        PluginParameter {
            name: "osm.useragent"
            value: "GeschwindigkeitsverlaufAusGPS/0.1 (Qt research application)"
        }
    }

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
                    text: "Route berechnen"
                    enabled: !routeSelector.busy && root.startValid && root.targetValid
                    highlighted: true
                    onClicked: routeSelector.calculateRoute()
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

            MapView {
                id: mapView
                Layout.fillWidth: true
                Layout.fillHeight: true
                map.plugin: osmPlugin
                map.center: QtPositioning.coordinate(48.743, 9.320)
                map.zoomLevel: 12

                // Qt exposes a custom tile host as the final supported map
                // type. Select it explicitly so the map cannot fall back to
                // an API-key protected third-party style.
                function activateCustomMapType() {
                    const mapTypes = map.supportedMapTypes
                    if (mapTypes.length > 0) {
                        map.activeMapType = mapTypes[mapTypes.length - 1]
                    }
                }

                Component.onCompleted: activateCustomMapType()

                Connections {
                    target: mapView.map

                    function onSupportedMapTypesChanged() {
                        mapView.activateCustomMapType()
                    }
                }

                MapRectangle {
                    id: regionRectangle
                    parent: mapView.map
                    visible: root.selectedRegion !== null
                    color: "#224070d8"
                    border.color: "#4050d0"
                    border.width: 2
                    topLeft: root.selectedRegion === null
                        ? QtPositioning.coordinate()
                        : QtPositioning.coordinate(
                            root.selectedRegion.north,
                            root.selectedRegion.west
                        )
                    bottomRight: root.selectedRegion === null
                        ? QtPositioning.coordinate()
                        : QtPositioning.coordinate(
                            root.selectedRegion.south,
                            root.selectedRegion.east
                        )
                }

                MapPolyline {
                    id: routeLine
                    parent: mapView.map
                    line.width: 6
                    line.color: "#1769d2"
                    opacity: 0.9
                }

                MapItemView {
                    parent: mapView.map
                    model: trafficSignalModel
                    autoFitViewport: false

                    delegate: MapQuickItem {
                        required property real latitude
                        required property real longitude
                        required property real distanceFromStartM

                        coordinate: QtPositioning.coordinate(latitude, longitude)
                        anchorPoint.x: signalMarker.width / 2
                        anchorPoint.y: signalMarker.height / 2

                        sourceItem: Rectangle {
                            id: signalMarker
                            width: 14
                            height: 14
                            radius: 3
                            color: "#e02b2b"
                            border.color: "white"
                            border.width: 2

                            ToolTip.visible: signalHover.hovered
                            ToolTip.text: "Ampel bei "
                                + Math.round(distanceFromStartM)
                                + " m"

                            HoverHandler { id: signalHover }
                        }
                    }
                }

                MapQuickItem {
                    id: startMarker
                    parent: mapView.map
                    visible: root.startValid
                    anchorPoint.x: startCircle.width / 2
                    anchorPoint.y: startCircle.height / 2

                    sourceItem: Rectangle {
                        id: startCircle
                        width: 24
                        height: 24
                        radius: 12
                        color: "#18883a"
                        border.color: "white"
                        border.width: 3
                    }
                }

                MapQuickItem {
                    id: targetMarker
                    parent: mapView.map
                    visible: root.targetValid
                    anchorPoint.x: targetCircle.width / 2
                    anchorPoint.y: targetCircle.height / 2

                    sourceItem: Rectangle {
                        id: targetCircle
                        width: 24
                        height: 24
                        radius: 12
                        color: "#c62828"
                        border.color: "white"
                        border.width: 3
                    }
                }

                TapHandler {
                    id: coordinateTapHandler
                    acceptedButtons: Qt.LeftButton
                    enabled: !routeSelector.busy

                    onSingleTapped: (eventPoint, button) => {
                        const coordinate = mapView.map.toCoordinate(eventPoint.position)
                        if (coordinate.isValid) {
                            routeSelector.selectPoint(
                                coordinate.latitude,
                                coordinate.longitude
                            )
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
                    color: "#ddffffff"
                    border.color: "#bbbbbb"
                    z: 1000

                    Label {
                        id: instructionLabel
                        anchors.centerIn: parent
                        text: !root.startValid
                            ? "1. Startpunkt anklicken"
                            : (!root.targetValid
                                ? "2. Zielpunkt anklicken"
                                : "3. Straßendaten wählen und Route berechnen")
                    }
                }
            }

            Pane {
                Layout.preferredWidth: 330
                Layout.fillHeight: true

                ColumnLayout {
                    anchors.fill: parent
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
                            : "Noch keine FGB-/GeoPackage-Datei gewählt"
                        wrapMode: Text.WrapAnywhere
                        color: routeSelector.roadsFile.length > 0
                            ? palette.text
                            : palette.placeholderText
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

                    Item { Layout.fillHeight: true }

                    Label {
                        Layout.fillWidth: true
                        text: "Die Route wird als route_result.json gespeichert. "
                            + "Darin stehen Koordinaten, maxspeed, Straßenklasse, "
                            + "Oberfläche und Ampelpositionen."
                        wrapMode: Text.WordWrap
                        color: palette.placeholderText
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
                text: "Startpunkt auf der Karte anklicken."
                elide: Text.ElideRight
            }
        }
    }

    Connections {
        target: routeSelector

        function onStatusChanged(message) {
            statusLabel.text = message
        }

        function onSelectionChanged(data) {
            if (data.points.length > 0) {
                root.startValid = true
                startMarker.coordinate = QtPositioning.coordinate(
                    data.points[0][0], data.points[0][1]
                )
            } else {
                root.startValid = false
            }

            if (data.points.length > 1) {
                root.targetValid = true
                targetMarker.coordinate = QtPositioning.coordinate(
                    data.points[1][0], data.points[1][1]
                )
            } else {
                root.targetValid = false
            }
            root.selectedRegion = data.bbox
        }

        function onRouteChanged(points) {
            const path = []
            for (let index = 0; index < points.length; ++index) {
                path.push(QtPositioning.coordinate(
                    points[index].latitude,
                    points[index].longitude
                ))
            }
            routeLine.path = path
        }

        function onSummaryChanged(summary) {
            root.routeSummary = summary
        }
    }
}
