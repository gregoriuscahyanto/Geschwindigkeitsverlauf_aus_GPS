import QtQuick
import QtQuick.Controls
import QtLocation
import QtPositioning

ApplicationWindow {
    visible: true
    width: 1000
    height: 700
    title: "GPS Route Selector"

    Plugin { id: osm; name: "osm" }

    Map {
        id: map
        anchors.fill: parent
        plugin: osm
        center: QtPositioning.coordinate(48.74, 9.32)
        zoomLevel: 12

        MapQuickItem {
            id: startMarker
            sourceItem: Rectangle { width: 16; height: 16; radius: 8; color: "green" }
        }
        MapQuickItem {
            id: targetMarker
            sourceItem: Rectangle { width: 16; height: 16; radius: 8; color: "red" }
        }

        MouseArea {
            anchors.fill: parent
            onClicked: {
                var c = map.toCoordinate(Qt.point(mouse.x, mouse.y))
                routeSelector.selectPoint(c.latitude, c.longitude)
            }
        }
    }

    Label {
        anchors.top: parent.top
        anchors.left: parent.left
        padding: 10
        text: "Klick 1: Start | Klick 2: Ziel"
    }

    Connections {
        target: routeSelector
        function onSelectionChanged(data) {
            if (data.points.length > 0)
                startMarker.coordinate = QtPositioning.coordinate(data.points[0][0], data.points[0][1])
            if (data.points.length > 1)
                targetMarker.coordinate = QtPositioning.coordinate(data.points[1][0], data.points[1][1])
        }
    }
}
