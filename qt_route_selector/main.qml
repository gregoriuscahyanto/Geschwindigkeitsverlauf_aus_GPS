import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtLocation
import QtPositioning
import OfflineMap 1.0

ApplicationWindow {
    id: root
    visible: true
    width: 1420
    height: 850
    minimumWidth: 1000
    minimumHeight: 650
    title: "GPS-Routen- und Geschwindigkeitsprofil"

    property var routeSummary: ({})
    property var mapSummary: ({})
    property var selectionBBox: null
    property bool onlineMode: routeSelector.mapMode === "online"

    function validSelectionBBox(box) {
        return box !== null
            && box !== undefined
            && box.north !== undefined
            && box.south !== undefined
            && box.east !== undefined
            && box.west !== undefined
    }

    function selectionTopLeft() {
        const box = root.selectionBBox
        if (!root.validSelectionBBox(box)) {
            return QtPositioning.coordinate()
        }
        return QtPositioning.coordinate(box.north, box.west)
    }

    function selectionBottomRight() {
        const box = root.selectionBBox
        if (!root.validSelectionBBox(box)) {
            return QtPositioning.coordinate()
        }
        return QtPositioning.coordinate(box.south, box.east)
    }

    function loadOfflineViewport() {
        if (routeSelector.roadsFile.length > 0 && !routeSelector.busy) {
            routeSelector.loadRoadMap(
                offlineMap.visibleBounds(), offlineMap.zoomLevel
            )
        }
    }

    function selectCustomMapType() {
        if (onlineMap.map.supportedMapTypes.length > 0) {
            onlineMap.map.activeMapType = onlineMap.map.supportedMapTypes[
                onlineMap.map.supportedMapTypes.length - 1
            ]
        }
    }

    function synchronizeMapMode() {
        if (root.onlineMode) {
            onlineMap.map.center = QtPositioning.coordinate(
                offlineMap.centerLatitude, offlineMap.centerLongitude
            )
            onlineMap.map.zoomLevel = offlineMap.zoomLevel
            customMapTypeTimer.restart()
        } else {
            offlineMap.centerLatitude = onlineMap.map.center.latitude
            offlineMap.centerLongitude = onlineMap.map.center.longitude
            offlineMap.zoomLevel = onlineMap.map.zoomLevel
            if (routeSelector.automaticOfflineReload) {
                offlineReloadTimer.restart()
            }
        }
    }

    function fitRoute() {
        if (root.onlineMode) {
            if (root.routeSummary.route_points !== undefined
                    && root.routeSummary.route_points > 1) {
                onlineMap.map.fitViewportToMapItems([onlineRoute])
            }
        } else {
            offlineMap.fitRoute()
        }
    }

    Plugin {
        id: osmPlugin
        name: "osm"

        PluginParameter {
            name: "osm.mapping.providersrepository.disabled"
            value: true
        }
        PluginParameter {
            name: "osm.mapping.custom.host"
            value: "https://tile.openstreetmap.org/%z/%x/%y.png"
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
            name: "osm.mapping.cache.disk.size"
            value: 512 * 1024 * 1024
        }
        PluginParameter {
            name: "osm.useragent"
            value: "GeschwindigkeitsverlaufAusGPS/0.2 (Qt research application)"
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
                spacing: 6

                Button {
                    text: "Straßendaten wählen"
                    enabled: !routeSelector.busy
                    onClicked: routeSelector.chooseRoadData()
                }

                Button {
                    text: "PBF-Schnellindex erstellen"
                    visible: routeSelector.isPbfSource
                    enabled: !routeSelector.busy
                    onClicked: routeSelector.buildPbfIndex()
                    ToolTip.visible: hovered
                    ToolTip.text: "Einmalige Konvertierung in ein räumlich indiziertes GeoPackage"
                }

                Button {
                    text: "Offline-Ausschnitt laden"
                    visible: !root.onlineMode
                    enabled: !routeSelector.busy
                        && routeSelector.roadsFile.length > 0
                    onClicked: root.loadOfflineViewport()
                }

                Button {
                    text: "Letzten Punkt entfernen"
                    enabled: !routeSelector.busy && routeSelector.pointCount > 0
                    onClicked: routeSelector.undoLastPoint()
                }

                Button {
                    text: "Route berechnen"
                    enabled: !routeSelector.busy
                        && routeSelector.pointCount >= 2
                        && routeSelector.roadsFile.length > 0
                    highlighted: true
                    onClicked: routeSelector.calculateRoute()
                }

                Button {
                    text: "Route einpassen"
                    enabled: !routeSelector.busy
                        && root.routeSummary.route_points !== undefined
                        && root.routeSummary.route_points > 1
                    onClicked: root.fitRoute()
                }

                Button {
                    text: "Zurücksetzen"
                    enabled: !routeSelector.busy
                    onClicked: routeSelector.resetSelection()
                }

                Item { Layout.fillWidth: true }

                Label { text: "Karte:" }
                ComboBox {
                    id: mapModeCombo
                    Layout.preferredWidth: 135
                    textRole: "text"
                    valueRole: "value"
                    model: [
                        {"text": "Automatisch", "value": "auto"},
                        {"text": "Online OSM", "value": "online"},
                        {"text": "Komplett offline", "value": "offline"}
                    ]
                    Component.onCompleted: {
                        for (let index = 0; index < model.length; ++index) {
                            if (model[index].value === routeSelector.mapPreference) {
                                currentIndex = index
                                break
                            }
                        }
                    }
                    onActivated: routeSelector.setMapPreference(currentValue)
                }

                Label { text: "Routing:" }
                ComboBox {
                    id: routingProfileCombo
                    Layout.preferredWidth: 190
                    textRole: "text"
                    valueRole: "value"
                    model: [
                        {"text": "Hauptstraßen bevorzugen", "value": "preferred"},
                        {"text": "Schnellste Route", "value": "fastest"},
                        {"text": "Kürzeste Route", "value": "shortest"}
                    ]
                    Component.onCompleted: {
                        for (let index = 0; index < model.length; ++index) {
                            if (model[index].value === routeSelector.routingProfile) {
                                currentIndex = index
                                break
                            }
                        }
                    }
                    onActivated: routeSelector.setRoutingProfile(currentValue)
                }

                BusyIndicator {
                    running: routeSelector.busy
                    visible: running
                    implicitWidth: 28
                    implicitHeight: 28
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

                MapView {
                    id: onlineMap
                    anchors.fill: parent
                    visible: root.onlineMode
                    map.plugin: osmPlugin
                    map.center: QtPositioning.coordinate(48.743, 9.320)
                    map.zoomLevel: 12

                    MapRectangle {
                        parent: onlineMap.map
                        visible: root.validSelectionBBox(root.selectionBBox)
                        color: "#224267d5"
                        border.color: "#4267d5"
                        border.width: 2
                        topLeft: root.selectionTopLeft()
                        bottomRight: root.selectionBottomRight()
                    }

                    MapPolyline {
                        id: onlineRoute
                        parent: onlineMap.map
                        line.width: 6
                        line.color: "#1769d2"
                    }

                    MapItemView {
                        parent: onlineMap.map
                        model: routePointModel
                        autoFitViewport: false

                        delegate: MapQuickItem {
                            required property real latitude
                            required property real longitude
                            required property string pointKind
                            required property string pointLabel

                            coordinate: QtPositioning.coordinate(latitude, longitude)
                            anchorPoint.x: marker.width / 2
                            anchorPoint.y: marker.height / 2

                            sourceItem: Rectangle {
                                id: marker
                                width: 24
                                height: 24
                                radius: 12
                                color: pointKind === "start"
                                    ? "#18883a"
                                    : (pointKind === "target" ? "#c62828" : "#ef8b1e")
                                border.color: "white"
                                border.width: 3

                                Label {
                                    anchors.centerIn: parent
                                    text: pointLabel
                                    color: "white"
                                    font.bold: true
                                    font.pixelSize: 10
                                }
                            }
                        }
                    }

                    MapItemView {
                        parent: onlineMap.map
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
                                width: 13
                                height: 13
                                radius: 3
                                color: "#e02b2b"
                                border.color: "white"
                                border.width: 2
                                ToolTip.visible: signalHover.hovered
                                ToolTip.text: "Ampel bei "
                                    + Math.round(distanceFromStartM) + " m"
                                HoverHandler { id: signalHover }
                            }
                        }
                    }

                    TapHandler {
                        parent: onlineMap.map
                        acceptedButtons: Qt.LeftButton
                        enabled: !routeSelector.busy
                        onSingleTapped: (eventPoint, button) => {
                            const coordinate = onlineMap.map.toCoordinate(
                                eventPoint.position, false
                            )
                            if (coordinate.isValid) {
                                routeSelector.selectPoint(
                                    coordinate.latitude, coordinate.longitude
                                )
                            }
                        }
                    }
                }

                OfflineMapItem {
                    id: offlineMap
                    anchors.fill: parent
                    visible: !root.onlineMode
                    centerLatitude: 48.743
                    centerLongitude: 9.320
                    zoomLevel: 12

                    onCoordinateClicked: (latitude, longitude) => {
                        if (!routeSelector.busy) {
                            routeSelector.selectPoint(latitude, longitude)
                        }
                    }
                    onViewportChanged: {
                        if (!root.onlineMode && routeSelector.automaticOfflineReload) {
                            offlineReloadTimer.restart()
                        }
                    }
                    onCenterChanged: {
                        if (!root.onlineMode) {
                            onlineMap.map.center = QtPositioning.coordinate(
                                centerLatitude, centerLongitude
                            )
                        }
                    }
                    onZoomLevelChanged: {
                        if (!root.onlineMode) {
                            onlineMap.map.zoomLevel = zoomLevel
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
                        text: routeSelector.pointCount === 0
                            ? "1. Startpunkt anklicken"
                            : (routeSelector.pointCount === 1
                                ? "2. Ziel oder Zwischenziel anklicken"
                                : "Weitere Zwischenziele möglich oder Route berechnen")
                    }
                }

                Column {
                    visible: !root.onlineMode
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
                        text: root.onlineMode
                            ? "Online OSM · Ziehen/zoomen · Klick: Punkt hinzufügen"
                            : "Offline · Ziehen/zoomen · Klick: Punkt hinzufügen"
                        color: "#4b5055"
                    }
                }
            }

            Pane {
                Layout.preferredWidth: 360
                Layout.fillHeight: true

                ScrollView {
                    anchors.fill: parent
                    contentWidth: availableWidth

                    ColumnLayout {
                        width: parent.width
                        spacing: 12

                        Label {
                            text: "Kartenmodus"
                            font.bold: true
                            font.pixelSize: 17
                        }
                        Label {
                            Layout.fillWidth: true
                            text: root.onlineMode ? "Online OpenStreetMap" : "Lokale Vektorkarte"
                            color: root.onlineMode ? "#187a32" : "#b45a00"
                            font.bold: true
                        }
                        Label {
                            Layout.fillWidth: true
                            text: routeSelector.mapModeReason
                            wrapMode: Text.WordWrap
                            color: palette.placeholderText
                        }

                        MenuSeparator { Layout.fillWidth: true }

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
                        Label {
                            visible: routeSelector.isPbfSource
                            Layout.fillWidth: true
                            text: "Direktes PBF-Lesen ist langsam, weil die Datei für räumliche "
                                + "Abfragen sequenziell durchsucht wird. Der Schnellindex wird nur einmal erstellt."
                            wrapMode: Text.WordWrap
                            color: "#b45a00"
                        }

                        GridLayout {
                            visible: !root.onlineMode
                            columns: 2
                            columnSpacing: 14
                            rowSpacing: 7

                            Label { text: "Kartenlinien:" }
                            Label {
                                text: root.mapSummary.display_lines === undefined
                                    ? "–" : root.mapSummary.display_lines
                            }
                            Label { text: "Kartenpunkte:" }
                            Label {
                                text: root.mapSummary.display_vertices === undefined
                                    ? "–" : root.mapSummary.display_vertices
                            }
                            Label { text: "Aus Cache:" }
                            Label {
                                text: root.mapSummary.cache_hit === undefined
                                    ? "–" : (root.mapSummary.cache_hit ? "Ja" : "Nein")
                            }
                            Label { text: "Anzeige begrenzt:" }
                            Label {
                                text: root.mapSummary.truncated === undefined
                                    ? "–" : (root.mapSummary.truncated ? "Ja" : "Nein")
                            }
                        }

                        MenuSeparator { Layout.fillWidth: true }

                        Label {
                            text: "Punkte und Route"
                            font.bold: true
                            font.pixelSize: 17
                        }
                        GridLayout {
                            columns: 2
                            columnSpacing: 14
                            rowSpacing: 8

                            Label { text: "Gewählte Punkte:" }
                            Label { text: routeSelector.pointCount }
                            Label { text: "Zwischenziele:" }
                            Label { text: Math.max(0, routeSelector.pointCount - 2) }
                            Label { text: "Teilstrecken:" }
                            Label {
                                text: root.routeSummary.legs === undefined
                                    ? "–" : root.routeSummary.legs
                            }
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
                                    ? "–" : root.routeSummary.road_segments
                            }
                            Label { text: "Ampeln:" }
                            Label {
                                text: root.routeSummary.traffic_signals === undefined
                                    ? "–" : root.routeSummary.traffic_signals
                            }
                            Label { text: "Graph aus Cache:" }
                            Label {
                                text: root.routeSummary.graph_cache_hit === undefined
                                    ? "–"
                                    : (root.routeSummary.graph_cache_hit ? "Ja" : "Nein")
                            }
                            Label { text: "Max. Snap:" }
                            Label {
                                text: root.routeSummary.max_snap_m === undefined
                                    ? "–" : Math.round(root.routeSummary.max_snap_m) + " m"
                            }
                        }

                        MenuSeparator { Layout.fillWidth: true }

                        Label {
                            Layout.fillWidth: true
                            text: "Standardmäßig wird die Online-OSM-Karte verwendet. "
                                + "Bei fehlender Verbindung schaltet die Automatik auf die lokale Vektorkarte. "
                                + "Routing und OSM-Auswertung bleiben immer lokal."
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
                text: "Online-OSM wird geprüft. Startpunkt kann bereits gewählt werden."
                elide: Text.ElideRight
            }
        }
    }

    Timer {
        id: customMapTypeTimer
        interval: 250
        repeat: false
        onTriggered: root.selectCustomMapType()
    }

    Timer {
        id: offlineReloadTimer
        interval: 650
        repeat: false
        onTriggered: {
            if (!root.onlineMode && routeSelector.automaticOfflineReload) {
                root.loadOfflineViewport()
            }
        }
    }

    Component.onCompleted: {
        customMapTypeTimer.start()
        root.synchronizeMapMode()
    }

    Connections {
        target: onlineMap.map

        function onMapReadyChanged() {
            if (onlineMap.map.mapReady) {
                customMapTypeTimer.restart()
            }
        }
        function onErrorChanged() {
            if (onlineMap.map.error === Map.ConnectionError) {
                routeSelector.reportOnlineMapError(onlineMap.map.errorString)
            }
        }
        function onCenterChanged() {
            if (root.onlineMode) {
                offlineMap.centerLatitude = onlineMap.map.center.latitude
                offlineMap.centerLongitude = onlineMap.map.center.longitude
            }
        }
        function onZoomLevelChanged() {
            if (root.onlineMode) {
                offlineMap.zoomLevel = onlineMap.map.zoomLevel
            }
        }
    }

    Connections {
        target: routeSelector

        function onStatusChanged(message) {
            statusLabel.text = message
        }
        function onMapModeChanged() {
            root.onlineMode = routeSelector.mapMode === "online"
            root.synchronizeMapMode()
        }
        function onRoadsFileChanged() {
            offlineMap.clearRoads()
            root.mapSummary = ({})
            if (!root.onlineMode && routeSelector.automaticOfflineReload) {
                offlineReloadTimer.restart()
            }
        }
        function onMapRoadsChanged(features) {
            offlineMap.setRoads(features)
        }
        function onMapSummaryChanged(summary) {
            root.mapSummary = summary
        }
        function onSelectionChanged(data) {
            root.selectionBBox = (
                data !== null
                && data !== undefined
                && data.bbox !== undefined
            ) ? data.bbox : null
            offlineMap.setSelection(data)
        }
        function onRouteChanged(points) {
            offlineMap.setRoute(points)
            onlineRoute.path = []
            for (let index = 0; index < points.length; ++index) {
                onlineRoute.addCoordinate(QtPositioning.coordinate(
                    points[index].latitude, points[index].longitude
                ))
            }
            if (points.length > 1) {
                Qt.callLater(root.fitRoute)
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
