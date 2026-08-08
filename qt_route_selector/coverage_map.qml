import QtQuick
import QtLocation
import QtPositioning

Item {
    id: root

    property var coverageAreas: []

    function coordinates(rawPath) {
        const result = []
        if (rawPath === undefined || rawPath === null) {
            return result
        }
        for (let index = 0; index < rawPath.length; ++index) {
            const point = rawPath[index]
            result.push(QtPositioning.coordinate(
                Number(point.latitude), Number(point.longitude)
            ))
        }
        return result
    }

    function areaColor(level) {
        if (level === "gpkg") {
            return "#4caf50"
        }
        if (level === "stale") {
            return "#f0a43a"
        }
        if (level === "pbf") {
            return "#4a90e2"
        }
        return "#b7bdc5"
    }

    function borderColor(level) {
        if (level === "gpkg") {
            return "#216b2d"
        }
        if (level === "stale") {
            return "#9b5b00"
        }
        if (level === "pbf") {
            return "#175a9e"
        }
        return "#6e747c"
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
            value: 256 * 1024 * 1024
        }
        PluginParameter {
            name: "osm.useragent"
            value: "GeschwindigkeitsverlaufAusGPS/0.8 (coverage map)"
        }
    }

    Map {
        id: coverageMap
        anchors.fill: parent
        plugin: osmPlugin
        center: QtPositioning.coordinate(48.1, 9.9)
        zoomLevel: 5.4

        MapItemView {
            model: root.coverageAreas

            delegate: MapPolygon {
                path: root.coordinates(modelData.path)
                color: root.areaColor(modelData.level)
                opacity: modelData.dataset === "dach" ? 0.30 : 0.60
                border.color: modelData.active
                    ? "#202020"
                    : root.borderColor(modelData.level)
                border.width: modelData.active
                    ? 4
                    : (modelData.dataset === "dach" ? 3 : 1.5)
            }
        }
    }

    Rectangle {
        anchors.left: parent.left
        anchors.bottom: parent.bottom
        anchors.margins: 12
        radius: 5
        color: "#e8ffffff"
        border.color: "#bbbbbb"
        width: mapHint.implicitWidth + 20
        height: mapHint.implicitHeight + 12

        Text {
            id: mapHint
            anchors.centerIn: parent
            text: "Ziehen / zoomen · Markierung zeigt lokal vorhandene Daten"
            color: "#4b5055"
            font.pixelSize: 12
        }
    }
}
