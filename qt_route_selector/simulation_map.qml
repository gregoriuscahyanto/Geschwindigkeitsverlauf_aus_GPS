import QtQuick
import QtQuick.Controls
import QtLocation
import QtPositioning

Rectangle {
    id: root
    color: "#e9ecef"

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

        Component.onCompleted: {
            if (supportedMapTypes.length > 0) {
                activeMapType = supportedMapTypes[supportedMapTypes.length - 1]
            }
        }

        MapPolyline {
            id: routeLine
            line.width: 5
            line.color: "#1769c2"
            path: simulationMapBridge.routePath
        }

        MapItemView {
            model: simulationMapBridge.trafficLights
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
            visible: simulationMapBridge.positionValid
            coordinate: QtPositioning.coordinate(
                simulationMapBridge.currentLatitude,
                simulationMapBridge.currentLongitude
            )
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
            target: simulationMapBridge
            function onRoutePathChanged() {
                routeLine.path = simulationMapBridge.routePath
                fitTimer.restart()
            }
        }

        Timer {
            id: fitTimer
            interval: 80
            repeat: false
            onTriggered: {
                if (simulationMapBridge.routePath.length > 1) {
                    map.fitViewportToMapItems([routeLine], Qt.rect(35, 35, 35, 35))
                }
            }
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
