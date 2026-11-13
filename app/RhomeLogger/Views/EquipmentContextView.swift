import SwiftUI
import SwiftData

/// Which physical station a load was read from.
///
/// This exists because it was the largest measured error source in the real
/// cold run, and because it is the one field that cannot be reconstructed
/// later — a stack number recalled months afterwards is not evidence. Asked
/// only for cable and machine work; a barbell needs no context and is never
/// interrupted for one.
struct EquipmentContextView: View {
    @Bindable var entry: ExerciseEntry
    let gym: String?

    @Environment(\.modelContext) private var context
    @Environment(\.dismiss) private var dismiss
    @State private var value: String = ""

    var body: some View {
        NavigationStack {
            List {
                Section {
                    TextField("e.g. Hammer Strength, by the window", text: $value)
                        .textInputAutocapitalization(.sentences)
                } header: {
                    Text(entry.exerciseName)
                } footer: {
                    Text("Name the machine however you'll recognise it next time — the label only has to be consistent, not official. Two machines of the same kind rarely agree on what their numbers mean, so the model treats each as its own scale.")
                }

                if !suggestions.isEmpty {
                    Section("Used before") {
                        ForEach(suggestions, id: \.self) { name in
                            Button {
                                value = name
                            } label: {
                                HStack {
                                    Text(name)
                                    Spacer()
                                    if name == value {
                                        Image(systemName: "checkmark")
                                            .foregroundStyle(.tint)
                                    }
                                }
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }
            }
            .navigationTitle("Which machine?")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Skip") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
                        entry.equipmentContext = trimmed.isEmpty ? nil : trimmed
                        try? context.save()
                        dismiss()
                    }
                }
            }
            .onAppear { value = entry.equipmentContext ?? "" }
        }
    }

    /// Stations previously recorded for this movement, this gym first.
    private var suggestions: [String] {
        let exerciseId = entry.exerciseId
        let descriptor = FetchDescriptor<ExerciseEntry>(
            predicate: #Predicate { $0.exerciseId == exerciseId }
        )
        guard let all = try? context.fetch(descriptor) else { return [] }

        let sorted = all.sorted {
            ($0.workout?.startedAt ?? .distantPast) > ($1.workout?.startedAt ?? .distantPast)
        }
        var here: [String] = []
        var elsewhere: [String] = []
        for candidate in sorted {
            guard let name = candidate.equipmentContext, !name.isEmpty else { continue }
            if let gym, candidate.workout?.gym == gym {
                if !here.contains(name) { here.append(name) }
            } else if !elsewhere.contains(name) {
                elsewhere.append(name)
            }
        }
        return here + elsewhere.filter { !here.contains($0) }
    }
}
