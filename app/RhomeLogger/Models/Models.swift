import Foundation
import SwiftData

/// The logged schema, written against `PRODUCT.md` §7.1 (version 0.5).
///
/// Two fields exist here that the athlete's previous logger did not carry, and
/// both were added because their absence was *measured* rather than suspected:
///
/// - `equipmentContext` — which physical station a load was read from. On the
///   99-session historical log the best naive predictor scored 0.0976 on free
///   weights and 0.1657 on cable/machine work; the gap is the labelling. It
///   cannot be reconstructed after the fact.
/// - `completedAt` on each set — `DATA.md` §18 has always required per-set
///   times and no source has ever supplied them. Within-session position is now
///   a model input, so this closes a standing gap.
///
/// `exerciseId` is a library identifier, never a free-typed name. The entire
/// L3.10 name-mapping exercise existed because the old logger used its own
/// vocabulary; logging against the library directly retires that class of
/// problem instead of re-solving it.

@Model
final class Workout {
    var id: UUID = UUID()
    var startedAt: Date = Date()
    var endedAt: Date?
    /// Free-text location. Coarse context; `ExerciseEntry.equipmentContext`
    /// carries the specific station where it matters.
    var gym: String?
    var notes: String = ""

    @Relationship(deleteRule: .cascade, inverse: \ExerciseEntry.workout)
    var entries: [ExerciseEntry] = []

    init(startedAt: Date = Date(), gym: String? = nil) {
        self.id = UUID()
        self.startedAt = startedAt
        self.gym = gym
    }

    /// Performed order is part of the observation — see `DATA.md` §18. Never
    /// sort these alphabetically; the audit caught exactly that once already.
    var orderedEntries: [ExerciseEntry] {
        entries.sorted { $0.order < $1.order }
    }

    var isFinished: Bool { endedAt != nil }

    var totalSets: Int {
        entries.reduce(0) { $0 + $1.sets.count }
    }
}

@Model
final class ExerciseEntry {
    var id: UUID = UUID()
    /// Canonical id from the bundled exercise library.
    var exerciseId: String = ""
    /// Denormalised for offline history display; `exerciseId` is authoritative.
    var exerciseName: String = ""
    /// Equipment class from the library, kept so an export can be read without
    /// re-joining the library.
    var equipment: String = ""
    /// Position within the session, zero-based.
    var order: Int = 0
    /// Which physical station this was. Required for cable and machine work,
    /// meaningless for free weights, and never demanded where it does not
    /// apply — see `PRODUCT.md` §7.1.
    var equipmentContext: String?

    var workout: Workout?

    @Relationship(deleteRule: .cascade, inverse: \LoggedSet.entry)
    var sets: [LoggedSet] = []

    init(exerciseId: String, exerciseName: String, equipment: String, order: Int) {
        self.id = UUID()
        self.exerciseId = exerciseId
        self.exerciseName = exerciseName
        self.equipment = equipment
        self.order = order
    }

    var orderedSets: [LoggedSet] {
        sets.sorted { $0.setNumber < $1.setNumber }
    }

    /// Cable stacks and machine selectors are labelled per-machine; a barbell
    /// is the same load anywhere.
    var needsEquipmentContext: Bool {
        equipment == "cable" || equipment == "machine"
    }
}

enum SetType: String, Codable, CaseIterable, Identifiable {
    case working
    case warmup
    case backoff
    case drop

    var id: String { rawValue }

    var label: String {
        switch self {
        case .working: return "Working"
        case .warmup: return "Warm-up"
        case .backoff: return "Back-off"
        case .drop: return "Drop"
        }
    }

    /// Per `PRODUCT.md` §7.1: warm-ups carry no dose, drop segments carry dose
    /// but are excluded from performance estimation.
    var countsTowardPerformance: Bool {
        self == .working || self == .backoff
    }
}

@Model
final class LoggedSet {
    var id: UUID = UUID()
    var setNumber: Int = 1
    var loadKg: Double = 0
    var reps: Int = 0
    /// Effort is stored as logged. RPE and RIR are not both required, and
    /// neither is invented when absent — an unrated set is imputed downstream
    /// per D18, which is a decision the engine makes explicitly.
    var rpe: Double?
    var rir: Double?
    var setTypeRaw: String = SetType.working.rawValue
    /// When this set actually finished. `DATA.md` §18.
    var completedAt: Date = Date()

    var entry: ExerciseEntry?

    init(
        setNumber: Int,
        loadKg: Double,
        reps: Int,
        rpe: Double? = nil,
        rir: Double? = nil,
        setType: SetType = .working,
        completedAt: Date = Date()
    ) {
        self.id = UUID()
        self.setNumber = setNumber
        self.loadKg = loadKg
        self.reps = reps
        self.rpe = rpe
        self.rir = rir
        self.setTypeRaw = setType.rawValue
        self.completedAt = completedAt
    }

    var setType: SetType {
        get { SetType(rawValue: setTypeRaw) ?? .working }
        set { setTypeRaw = newValue.rawValue }
    }
}
