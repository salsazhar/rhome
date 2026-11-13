import Foundation
import SwiftData

/// The export the Python side ingests.
///
/// Deliberately verbose and self-describing: it carries its own schema version
/// and the library version it was logged against, so a file found later can be
/// read without guessing what produced it. `data/real_manifest.json` exists for
/// the same reason on the other side.
struct SessionExport: Codable {
    static let schemaVersion = "rhome-logger/1"
    static let libraryVersion = "v1.2"

    struct Set: Codable {
        let setNumber: Int
        let loadKg: Double
        let reps: Int
        let rpe: Double?
        let rir: Double?
        let setType: String
        let completedAt: Date
    }

    struct Entry: Codable {
        let exerciseId: String
        let exerciseName: String
        let equipment: String
        let order: Int
        let equipmentContext: String?
        let sets: [Set]
    }

    struct Session: Codable {
        let id: String
        let startedAt: Date
        let endedAt: Date?
        let gym: String?
        let notes: String
        let entries: [Entry]
    }

    let schemaVersion: String
    let libraryVersion: String
    let exportedAt: Date
    let sessions: [Session]

    init(sessions: [Session]) {
        self.schemaVersion = Self.schemaVersion
        self.libraryVersion = Self.libraryVersion
        self.exportedAt = Date()
        self.sessions = sessions
    }
}

enum SessionExporter {
    static func build(from workouts: [Workout]) -> SessionExport {
        let sessions = workouts
            .sorted { $0.startedAt < $1.startedAt }
            .map { workout in
                SessionExport.Session(
                    id: workout.id.uuidString,
                    startedAt: workout.startedAt,
                    endedAt: workout.endedAt,
                    gym: workout.gym,
                    notes: workout.notes,
                    entries: workout.orderedEntries.map { entry in
                        SessionExport.Entry(
                            exerciseId: entry.exerciseId,
                            exerciseName: entry.exerciseName,
                            equipment: entry.equipment,
                            order: entry.order,
                            equipmentContext: entry.equipmentContext,
                            sets: entry.orderedSets.map { set in
                                SessionExport.Set(
                                    setNumber: set.setNumber,
                                    loadKg: set.loadKg,
                                    reps: set.reps,
                                    rpe: set.rpe,
                                    rir: set.rir,
                                    setType: set.setType.rawValue,
                                    completedAt: set.completedAt
                                )
                            }
                        )
                    }
                )
            }
        return SessionExport(sessions: sessions)
    }

    private static func encoded(_ export: SessionExport) throws -> Data {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        encoder.dateEncodingStrategy = .iso8601
        return try encoder.encode(export)
    }

    private static var filename: String {
        let stamp = ISO8601DateFormatter()
        stamp.formatOptions = [.withFullDate]
        return "rhome_log_\(stamp.string(from: Date())).json"
    }

    /// Writes to a temporary file and returns its URL, for the share sheet.
    static func writeJSON(_ export: SessionExport) throws -> URL {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent(filename)
        try encoded(export).write(to: url, options: .atomic)
        return url
    }

    /// Writes the whole log into the app's Documents folder, which
    /// `UIFileSharingEnabled` surfaces in Files under *On My iPhone → Rhome*.
    ///
    /// iOS sandboxing means nothing reaches the development machine on its own;
    /// this only removes the share sheet from the loop, so the file is already
    /// sitting there whenever it is wanted. Rewritten in full each time — the
    /// store on the device stays authoritative and this is a derived artefact,
    /// exactly as `data/real_export/` is on the other side.
    @discardableResult
    static func writeToDocuments(_ export: SessionExport) throws -> URL {
        let documents = try FileManager.default.url(
            for: .documentDirectory, in: .userDomainMask,
            appropriateFor: nil, create: true
        )
        let url = documents.appendingPathComponent("rhome_log.json")
        try encoded(export).write(to: url, options: .atomic)
        return url
    }
}
