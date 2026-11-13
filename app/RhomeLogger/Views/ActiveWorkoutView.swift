import SwiftUI
import SwiftData

struct ActiveWorkoutView: View {
    @Bindable var workout: Workout

    @Environment(\.modelContext) private var context
    @Environment(\.dismiss) private var dismiss

    @State private var showingPicker = false
    @State private var pendingContext: ExerciseEntry?
    @State private var editingSet: LoggedSet?
    @State private var entryPendingRemoval: ExerciseEntry?
    @State private var confirmingDiscard = false

    var body: some View {
        List {
            ForEach(workout.orderedEntries) { entry in
                Section {
                    ForEach(entry.orderedSets) { set in
                        Button {
                            editingSet = set
                        } label: {
                            SetRow(set: set)
                        }
                        .buttonStyle(.plain)
                    }
                    .onDelete { offsets in
                        delete(offsets, from: entry)
                    }

                    Button {
                        addSet(to: entry)
                    } label: {
                        Label("Add set", systemImage: "plus")
                            .font(.subheadline)
                    }
                } header: {
                    EntryHeader(
                        entry: entry,
                        onEditContext: { pendingContext = entry },
                        onRemove: { entryPendingRemoval = entry }
                    )
                }
            }

            Section {
                Button {
                    showingPicker = true
                } label: {
                    Label("Add exercise", systemImage: "plus.circle")
                }

                if !workout.isFinished {
                    Button {
                        finish()
                    } label: {
                        Label("Finish session", systemImage: "checkmark.circle")
                    }
                    .disabled(workout.totalSets == 0)

                    Button(role: .destructive) {
                        confirmingDiscard = true
                    } label: {
                        Label("Discard session", systemImage: "trash")
                    }
                }
            } footer: {
                if !workout.isFinished {
                    Text("Discarding removes the session and everything in it. Swipe a set to delete it; use the ••• beside an exercise to remove the exercise.")
                }
            }
        }
        .navigationTitle(workout.isFinished ? "Session" : "Logging")
        .navigationBarTitleDisplayMode(.inline)
        .sheet(isPresented: $showingPicker) {
            ExercisePickerView { chosen in
                add(chosen)
            }
        }
        .sheet(item: $pendingContext) { entry in
            EquipmentContextView(entry: entry, gym: workout.gym)
        }
        .sheet(item: $editingSet) { set in
            SetEditorView(set: set)
        }
        .confirmationDialog(
            "Remove \(entryPendingRemoval?.exerciseName ?? "this exercise")?",
            isPresented: .init(
                get: { entryPendingRemoval != nil },
                set: { if !$0 { entryPendingRemoval = nil } }
            ),
            titleVisibility: .visible
        ) {
            Button("Remove exercise and its sets", role: .destructive) {
                if let entry = entryPendingRemoval { remove(entry) }
                entryPendingRemoval = nil
            }
            Button("Keep", role: .cancel) { entryPendingRemoval = nil }
        }
        .confirmationDialog(
            "Discard this session?",
            isPresented: $confirmingDiscard,
            titleVisibility: .visible
        ) {
            Button("Discard session", role: .destructive) { discard() }
            Button("Keep logging", role: .cancel) {}
        } message: {
            Text("\(workout.entries.count) exercises and \(workout.totalSets) sets will be deleted.")
        }
    }

    private func add(_ chosen: LibraryExercise) {
        let entry = ExerciseEntry(
            exerciseId: chosen.id,
            exerciseName: chosen.name,
            equipment: chosen.equipment,
            order: workout.entries.count
        )
        entry.workout = workout
        workout.entries.append(entry)
        // Carry forward the station last used for this movement in this gym,
        // so the athlete confirms rather than retypes.
        entry.equipmentContext = lastContext(for: chosen.id)
        context.insert(entry)
        try? context.save()

        if entry.needsEquipmentContext && entry.equipmentContext == nil {
            pendingContext = entry
        }
    }

    /// Most recent station recorded for this exercise at this gym.
    private func lastContext(for exerciseId: String) -> String? {
        let descriptor = FetchDescriptor<ExerciseEntry>(
            predicate: #Predicate { $0.exerciseId == exerciseId }
        )
        guard let all = try? context.fetch(descriptor) else { return nil }
        let candidates = all
            .filter { $0.equipmentContext != nil }
            .filter { entry in
                guard let gym = workout.gym else { return true }
                return entry.workout?.gym == gym
            }
            .sorted { ($0.workout?.startedAt ?? .distantPast) > ($1.workout?.startedAt ?? .distantPast) }
        return candidates.first?.equipmentContext
    }

    private func addSet(to entry: ExerciseEntry) {
        let previous = entry.orderedSets.last
        let set = LoggedSet(
            setNumber: (previous?.setNumber ?? 0) + 1,
            loadKg: previous?.loadKg ?? 0,
            reps: previous?.reps ?? 0,
            rpe: previous?.rpe,
            rir: previous?.rir,
            setType: previous?.setType ?? .working
        )
        set.entry = entry
        entry.sets.append(set)
        context.insert(set)
        try? context.save()
        editingSet = set
    }

    private func delete(_ offsets: IndexSet, from entry: ExerciseEntry) {
        let ordered = entry.orderedSets
        for index in offsets {
            context.delete(ordered[index])
        }
        try? context.save()
        // Keep set numbers contiguous, so the exported sequence means what it says.
        for (i, set) in entry.orderedSets.enumerated() {
            set.setNumber = i + 1
        }
        try? context.save()
    }

    /// Removing an exercise renumbers the rest. Session position is a model
    /// input, so a gap here would be a gap in the evidence.
    private func remove(_ entry: ExerciseEntry) {
        context.delete(entry)
        try? context.save()
        for (i, remaining) in workout.orderedEntries.enumerated() {
            remaining.order = i
        }
        try? context.save()
    }

    private func discard() {
        context.delete(workout)
        try? context.save()
        dismiss()
    }

    private func finish() {
        workout.endedAt = Date()
        try? context.save()
        refreshDocumentsExport()
        dismiss()
    }

    /// Keeps Files > On My iPhone > Rhome current without needing the share
    /// sheet. Failure here is not worth interrupting a session for — the store
    /// is authoritative and the export can always be regenerated.
    private func refreshDocumentsExport() {
        let descriptor = FetchDescriptor<Workout>()
        guard let all = try? context.fetch(descriptor) else { return }
        let finished = all.filter(\.isFinished)
        try? SessionExporter.writeToDocuments(SessionExporter.build(from: finished))
    }
}

private struct EntryHeader: View {
    let entry: ExerciseEntry
    let onEditContext: () -> Void
    let onRemove: () -> Void

    var body: some View {
        HStack(alignment: .firstTextBaseline) {
            VStack(alignment: .leading, spacing: 4) {
                Text(entry.exerciseName)
                    .font(.headline)
                    .textCase(nil)

                if entry.needsEquipmentContext {
                    Button(action: onEditContext) {
                        HStack(spacing: 4) {
                            Image(systemName: entry.equipmentContext == nil
                                  ? "exclamationmark.triangle.fill" : "wrench.and.screwdriver")
                            Text(entry.equipmentContext ?? "Which machine?")
                        }
                        .font(.caption)
                        .foregroundStyle(entry.equipmentContext == nil ? .orange : .secondary)
                        .textCase(nil)
                    }
                }
            }

            Spacer()

            Menu {
                if entry.needsEquipmentContext {
                    Button {
                        onEditContext()
                    } label: {
                        Label("Change machine", systemImage: "wrench.and.screwdriver")
                    }
                }
                Button(role: .destructive) {
                    onRemove()
                } label: {
                    Label("Remove exercise", systemImage: "trash")
                }
            } label: {
                Image(systemName: "ellipsis.circle")
                    .font(.body)
                    .foregroundStyle(.secondary)
                    .frame(width: 44, height: 32)
                    .contentShape(Rectangle())
            }
        }
        .padding(.vertical, 2)
    }
}

private struct SetRow: View {
    let set: LoggedSet

    var body: some View {
        HStack(spacing: 12) {
            Text("\(set.setNumber)")
                .font(.caption.monospacedDigit())
                .foregroundStyle(.secondary)
                .frame(width: 18)

            Text(set.loadKg == 0 ? "BW" : "\(set.loadKg.clean) kg")
                .font(.body.monospacedDigit())
                .frame(width: 78, alignment: .leading)

            Text("\(set.reps) reps")
                .font(.body.monospacedDigit())

            Spacer()

            if let rpe = set.rpe {
                Text("RPE \(rpe.clean)")
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(.secondary)
            } else if let rir = set.rir {
                Text("RIR \(rir.clean)")
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(.secondary)
            }

            if set.setType != .working {
                Text(set.setType.label)
                    .font(.caption2)
                    .padding(.horizontal, 5)
                    .padding(.vertical, 2)
                    .background(.quaternary, in: Capsule())
            }
        }
        .contentShape(Rectangle())
    }
}

extension Double {
    /// 22.5 -> "22.5", 60.0 -> "60"
    var clean: String {
        self == rounded() ? String(Int(self)) : String(format: "%.1f", self)
    }
}
