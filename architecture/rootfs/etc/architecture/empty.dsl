workspace "Architecture" "No model yet: workspace.dsl is missing in the configured folder below /config. / Noch kein Modell: workspace.dsl fehlt im eingestellten Ordner unter /config." {
    model {
        user = person "User"
    }
    views {
        systemLandscape "landscape" {
            include *
            autolayout lr
        }
    }
}
