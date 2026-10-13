workspace "Architektur" "Noch kein Modell: /config/architektur/workspace.dsl fehlt." {
    model {
        michael = person "Michael"
    }
    views {
        systemLandscape "landschaft" {
            include *
            autolayout lr
        }
    }
}
