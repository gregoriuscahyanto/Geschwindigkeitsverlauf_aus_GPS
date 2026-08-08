import QtQuick
import QtQuick.Controls
import QtLocation
import QtPositioning

Rectangle {
    id: root
    color: "#e9ecef"

    // Context properties can briefly become null while QQuickWidget tears down.
    // Keep every binding safe so shutdown/reparenting never produces TypeErrors.
    property var bridge: (typeof simulationMapBridge !== "undefined" && simulationMapBridge)
        ? simulationMapBridge : null

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
            name: "osm.useragent"
            value: "GPSDrivingSimulation/1.0"
        }
    }

    Map {
        id: map
        anchors.fill: parent
        plugin: osmPlugin
        center: QtPositioning.coordinate(48.74, 9.31)
        zoomLevel: 11

        function mercatorY(latitude) {
            const clipped = Math.max(-85.05112878, Math.min(85.05112878, latitude))
            const radians = clipped * Math.PI / 180.0
            return Math.log(Math.tan(Math.PI / 4.0 + radians / 2.0))
        }

        function fitRoute() {
            if (!root.bridge) {
                return
            }
            const path = root.bridge.routePath
            if (!path || path.length < 2 || width < 10 || height < 10) {
                return
            }

            let minLatitude = 90.0
            let maxLatitude = -90.0
            let minLongitude = 180.0
            let maxLongitude = -180.0
            for (let index = 0; index < path.length; ++index) {
                minLatitude = Math.min(minLatitude, path[index].latitude)
                maxLatitude = Math.max(maxLatitude, path[index].latitude)
                minLongitude = Math.min(minLongitude, path[index].longitude)
                maxLongitude = Math.max(maxLongitude, path[index].longitude)
            }

            const centerLatitude = (minLatitude + maxLatitude) / 2.0
            const centerLongitude = (minLongitude + maxLongitude) / 2.0
            center = QtPositioning.coordinate(centerLatitude, centerLongitude)

            const longitudeSpan = Math.max(maxLongitude - minLongitude, 0.0001)
            const mercatorSpan = Math.max(
                Math.abs(mercatorY(maxLatitude) - mercatorY(minLatitude)),
                0.000001
            )
            const usableWidth = Math.max(200.0, width - 90.0)
            const usableHeight = Math.max(140.0, height - 80.0)
            const paddingFactor = 1.20
            const zoomLongitude = Math.log(
                usableWidth * 360.0 / (256.0 * longitudeSpan * paddingFactor)
            ) / Math.LN2
            const zoomLatitude = Math.log(
                usableHeight * 2.0 * Math.PI / (256.0 * mercatorSpan * paddingFactor)
            ) / Math.LN2
            zoomLevel = Math.max(3.0, Math.min(18.0, Math.min(zoomLongitude, zoomLatitude)))
        }

        Component.onCompleted: {
            if (supportedMapTypes.length > 0) {
                activeMapType = supportedMapTypes[supportedMapTypes.length - 1]
            }
            fitTimer.restart()
        }
        onWidthChanged: fitTimer.restart()
        onHeightChanged: fitTimer.restart()

        MapPolyline {
            id: routeLine
            line.width: 5
            line.color: "#1769c2"
            path: root.bridge ? root.bridge.routePath : []
        }

        MapItemView {
            model: root.bridge ? root.bridge.trafficLights : []
            delegate: MapQuickItem {
                required property var modelData
                coordinate: modelData
                anchorPoint.x: lightMarker.width / 2
                anchorPoint.y: lightMarker.height / 2
                sourceItem: Rectangle {
                    id: lightMarker
                    width: 11
                    height: 11
                    radius: 6
                    color: "#d52b2b"
                    border.color: "white"
                    border.width: 2
                }
            }
        }

        MapQuickItem {
            visible: root.bridge ? root.bridge.positionValid : false
            coordinate: root.bridge
                ? QtPositioning.coordinate(
                    root.bridge.currentLatitude,
                    root.bridge.currentLongitude
                )
                : QtPositioning.coordinate(0.0, 0.0)
            anchorPoint.x: currentMarker.width / 2
            anchorPoint.y: currentMarker.height / 2
            sourceItem: Rectangle {
                id: currentMarker
                width: 18
                height: 18
                radius: 9
                color: "#ff9118"
                border.color: "white"
                border.width: 3
            }
        }

        Connections {
            target: root.bridge
            ignoreUnknownSignals: true
            function onRoutePathChanged() {
                fitTimer.restart()
            }
        }

        Timer {
            id: fitTimer
            interval: 300
            repeat: false
            onTriggered: map.fitRoute()
        }
    }

    Label {
        anchors.left: parent.left
        anchors.bottom: parent.bottom
        anchors.margins: 7
        padding: 4
        text: "© OpenStreetMap contributors"
        font.pixelSize: 11
        background: Rectangle {
            color: "#d9ffffff"
            radius: 3
        }
    }

    Label {
        anchors.centerIn: parent
        visible: map.error === Map.ConnectionError
        text: "Online-Karte nicht erreichbar – Route und Positionsmarker bleiben verfügbar"
        color: "#555"
        padding: 8
        background: Rectangle {
            color: "#ddffffff"
            radius: 4
        }
    }
}
