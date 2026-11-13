import SwiftUI
import SwiftData

struct WorkoutListView: View {
    @Environment(\.modelContext) private var context
    @Query(sort: \Workout.startedAt, order: .reverse) private var workouts: [Workout]

    @State private var active: Workout?
    @State private var showingGymPrompt = false
    @State private var exportURL: URL?
    @State private var exportError: String?
    @State private var discarding: Workout?

    private var inProgress: Workout? { workouts.first { !$0.isFinished } }

    var body: some View {
        NavigationStack {
            List {
                if let session = inProgress {
                    Section {
                        Button {
                            active = session
                        } label: {
                            HStack {
                                VStack(alignment: .leading, spacing: 2) {
                                    Text("Session in progress")
                                        .font(.headline)
                                    Text("\(session.entries.count) exercises · \(session.totalSets) sets")
                                        .font(.subheadline)
                                        .foregroundStyle(.secondary)
                                }
                                Spacer()
                                Image(systemName: "chevron.right")
                                    .foregroundStyle(.tertiary)
                            }
                        }
                        .swipeActions(edge: .trailing) {
                            Button(role: .destructive) {
                                discarding = session
                            } label: {
                                Label("Discard", systemImage: "trash")
                            }
                        }
                    } footer: {
                        Text("Started by accident? Swipe it away.")
                    }
                }

                Section("History") {
                    if workouts.filter(\.isFinished).isEmpty {
                        Text("No sessions logged yet.")
                            .foregroundStyle(.secondary)
                    }
                    ForEach(workouts.filter(\.isFinished)) { workout in
                        NavigationLink {
                            ActiveWorkoutView(workout: workout)
                        } label: {
                            WorkoutRow(workout: workout)
                        }
                    }
                    .onDelete(perform: delete)
                }
            }
            .navigationTitle("Rhome")
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button {
                        export()
                    } label: {
                        Image(systemName: "square.and.arrow.up")
                    }
                    .disabled(workouts.isEmpty)
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        showingGymPrompt = true
                    } label: {
                        Label("Start", systemImage: "plus.circle.fill")
                    }
                    .disabled(inProgress != nil)
                }
            }
            .navigationDestination(item: $active) { workout in
                ActiveWorkoutView(workout: workout)
            }
            .sheet(isPresented: $showingGymPrompt) {
                GymPromptView(recentGyms: recentGyms) { gym in
                    start(gym: gym)
                }
            }
            .sheet(item: $exportURL) { url in
                ShareSheet(items: [url])
            }
            .alert("Export failed", isPresented: .constant(exportError != nil)) {
                Button("OK") { exportError = nil }
            } message: {
                Text(exportError ?? "")
            }
            .confirmationDialog(
                "Discard this session?",
                isPresented: .init(
                    get: { discarding != nil },
                    set: { if !$0 { discarding = nil } }
                ),
                titleVisibility: .visible
            ) {
                Button("Discard", role: .destructive) {
                    if let session = discarding {
                        context.delete(session)
                        try? context.save()
                        refreshDocumentsExport()
                    }
                    discarding = nil
                }
                Button("Keep", role: .cancel) { discarding = nil }
            } message: {
                if let session = discarding {
                    Text("\(session.entries.count) exercises and \(session.totalSets) sets will be deleted.")
                }
            }
        }
    }

    private var recentGyms: [String] {
        var seen: [String] = []
        for workout in workouts {
            if let gym = workout.gym, !gym.isEmpty, !seen.contains(gym) {
                seen.append(gym)
            }
        }
        return seen
    }

    private func start(gym: String?) {
        let workout = Workout(gym: gym)
        context.insert(workout)
        try? context.save()
        active = workout
    }

    private func delete(at offsets: IndexSet) {
        let finished = workouts.filter(\.isFinished)
        for index in offsets {
            context.delete(finished[index])
        }
        try? context.save()
        refreshDocumentsExport()
    }

    private func export() {
        do {
            let payload = SessionExporter.build(from: workouts.filter(\.isFinished))
            try SessionExporter.writeToDocuments(payload)
            exportURL = try SessionExporter.writeJSON(payload)
        } catch {
            exportError = error.localizedDescription
        }
    }

    /// A deletion has to reach the exported file too, or Files would keep
    /// offering a session that no longer exists.
    private func refreshDocumentsExport() {
        try? SessionExporter.writeToDocuments(
            SessionExporter.build(from: workouts.filter(\.isFinished))
        )
    }
}

private struct WorkoutRow: View {
    let workout: Workout

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            HStack {
                Text(workout.startedAt, format: .dateTime.weekday().day().month())
                    .font(.headline)
                if let gym = workout.gym, !gym.isEmpty {
                    Text(gym)
                        .font(.caption)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(.quaternary, in: Capsule())
                }
            }
            Text("\(workout.entries.count) exercises · \(workout.totalSets) sets")
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
    }
}

private struct GymPromptView: View {
    let recentGyms: [String]
    let onStart: (String?) -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var gym: String = ""

    var body: some View {
        NavigationStack {
            List {
                Section {
                    TextField("Gym", text: $gym)
                        .textInputAutocapitalization(.words)
                } header: {
                    Text("Where are you training?")
                } footer: {
                    Text("Recorded so cable and machine loads can be compared only against the same room. A barbell is the same weight anywhere; a stack marked 14 is not.")
                }

                if !recentGyms.isEmpty {
                    Section("Recent") {
                        ForEach(recentGyms, id: \.self) { name in
                            Button(name) { gym = name }
                        }
                    }
                }
            }
            .navigationTitle("New session")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Start") {
                        let trimmed = gym.trimmingCharacters(in: .whitespacesAndNewlines)
                        onStart(trimmed.isEmpty ? nil : trimmed)
                        dismiss()
                    }
                }
            }
        }
    }
}

extension URL: @retroactive Identifiable {
    public var id: String { absoluteString }
}

struct ShareSheet: UIViewControllerRepresentable {
    let items: [Any]

    func makeUIViewController(context: Context) -> UIActivityViewController {
        UIActivityViewController(activityItems: items, applicationActivities: nil)
    }

    func updateUIViewController(_ controller: UIActivityViewController, context: Context) {}
}
