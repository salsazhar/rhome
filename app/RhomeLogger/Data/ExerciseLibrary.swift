import Foundation

/// One row of the curated exercise library, pinned at v1.2.
///
/// The app logs against these identifiers directly. Nothing here is typed by
/// hand at logging time, so no name ever needs matching to the model's
/// vocabulary afterwards.
struct LibraryExercise: Identifiable, Hashable {
    let id: String          // exercise_id
    let name: String
    let movementPattern: String
    let equipment: String
    let primaryMuscles: [String]
    let secondaryMuscles: [String]

    var needsEquipmentContext: Bool {
        equipment == "cable" || equipment == "machine"
    }

    var muscleSummary: String {
        primaryMuscles.map { $0.replacingOccurrences(of: "_", with: " ") }
            .joined(separator: ", ")
    }
}

@MainActor
final class ExerciseLibrary: ObservableObject {
    static let shared = ExerciseLibrary()

    @Published private(set) var exercises: [LibraryExercise] = []
    private var byId: [String: LibraryExercise] = [:]

    private init() {
        load()
    }

    func exercise(id: String) -> LibraryExercise? { byId[id] }

    /// Substring match over name, then equipment, then muscle. Ranked so that
    /// a prefix hit on the name beats an incidental muscle match.
    func search(_ query: String, limit: Int = 60) -> [LibraryExercise] {
        let q = query.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard !q.isEmpty else { return Array(exercises.prefix(limit)) }

        var scored: [(Int, LibraryExercise)] = []
        for ex in exercises {
            let name = ex.name.lowercased()
            var score: Int?
            if name.hasPrefix(q) {
                score = 0
            } else if name.contains(q) {
                score = 1
            } else if ex.equipment.lowercased().contains(q) {
                score = 2
            } else if ex.primaryMuscles.contains(where: { $0.contains(q) }) {
                score = 3
            } else if ex.secondaryMuscles.contains(where: { $0.contains(q) }) {
                score = 4
            }
            if let score { scored.append((score, ex)) }
        }
        return scored
            .sorted { ($0.0, $0.1.name) < ($1.0, $1.1.name) }
            .prefix(limit)
            .map(\.1)
    }

    private func load() {
        guard let url = Bundle.main.url(forResource: "exercise_library", withExtension: "csv"),
              let raw = try? String(contentsOf: url, encoding: .utf8)
        else {
            assertionFailure("exercise_library.csv missing from the bundle")
            return
        }

        var rows = raw.split(separator: "\n", omittingEmptySubsequences: true)
        guard !rows.isEmpty else { return }

        let header = rows.removeFirst().split(separator: ",", omittingEmptySubsequences: false).map(String.init)
        let index = Dictionary(uniqueKeysWithValues: header.enumerated().map { ($1, $0) })

        func field(_ cols: [String], _ key: String) -> String {
            guard let i = index[key], i < cols.count else { return "" }
            return cols[i]
        }
        func muscles(_ cols: [String], _ key: String) -> [String] {
            field(cols, key).split(separator: "|").map(String.init).filter { !$0.isEmpty }
        }

        var parsed: [LibraryExercise] = []
        parsed.reserveCapacity(rows.count)
        for row in rows {
            let cols = row.split(separator: ",", omittingEmptySubsequences: false).map(String.init)
            let id = field(cols, "exercise_id")
            guard !id.isEmpty else { continue }
            parsed.append(
                LibraryExercise(
                    id: id,
                    name: field(cols, "name"),
                    movementPattern: field(cols, "movement_pattern"),
                    equipment: field(cols, "equipment"),
                    primaryMuscles: muscles(cols, "primary_muscles"),
                    secondaryMuscles: muscles(cols, "secondary_muscles")
                )
            )
        }

        exercises = parsed.sorted { $0.name < $1.name }
        byId = Dictionary(uniqueKeysWithValues: parsed.map { ($0.id, $0) })
    }
}
