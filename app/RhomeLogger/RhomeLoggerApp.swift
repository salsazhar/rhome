import SwiftUI
import SwiftData

@main
struct RhomeLoggerApp: App {
    var body: some Scene {
        WindowGroup {
            WorkoutListView()
        }
        .modelContainer(for: [Workout.self, ExerciseEntry.self, LoggedSet.self])
    }
}
