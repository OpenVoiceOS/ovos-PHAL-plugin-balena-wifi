import QtQuick.Layouts 1.15
import QtQuick 2.15
import QtQuick.Controls 2.15
import org.kde.kirigami 2.19 as Kirigami
import Mycroft 1.0 as Mycroft

Mycroft.Delegate {
    id: mainLoaderView

    property var pageType: sessionData.page_type
    leftPadding: 0
    rightPadding: 0
    bottomPadding: 0
    topPadding: 0

    contentItem: Loader {
        id: rootLoader
    }

    onPageTypeChanged: {
        console.log(sessionData.page_type)
        rootLoader.setSource(sessionData.page_type + ".qml")
    }
}
