import SwiftUI
import SwiftData

struct SetEditorView: View {
    @Bindable var set: LoggedSet

    @Environment(\.modelContext) private var context
    @Environment(\.dismiss) private var dismiss

    @State private var loadText: String = ""
    @State private var repsText: String = ""
    @State private var effort: Double = 9
    @State private var hasEffort = true
    @State private var setType: SetType = .working

    @FocusState private var focus: Field?
    private enum Field { case load, reps }

    private var load: Double { Double(loadText.replacingOccurrences(of: ",", with: ".")) ?? 0 }
    private var reps: Int { Int(repsText) ?? 0 }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    NumberField(
                        text: $loadText,
                        suffix: "kg",
                        keyboard: .decimalPad,
                        step: 2.5,
                        placeholder: "0"
                    )
                    .focused($focus, equals: .load)
                } header: {
                    Text("Load")
                } footer: {
                    Text(load == 0 ? "Zero is logged as bodyweight." : "")
                }

                Section("Reps") {
                    NumberField(
                        text: $repsText,
                        suffix: "reps",
                        keyboard: .numberPad,
                        step: 1,
                        placeholder: "0"
                    )
                    .focused($focus, equals: .reps)
                }

                Section {
                    Toggle("Recorded", isOn: $hasEffort)
                    if hasEffort {
                        VStack(alignment: .leading, spacing: 6) {
                            Text("RPE \(effort.clean)")
                                .font(.title3.monospacedDigit())
                            Slider(value: $effort, in: 5...10, step: 0.5)
                        }
                    }
                } header: {
                    Text("Effort")
                } footer: {
                    Text(hasEffort
                         ? "How close to failure the set finished. 10 is nothing left."
                         : "Left unrecorded. The model imputes it and marks the set as imputed rather than treating it as measured.")
                }

                Section("Type") {
                    Picker("Set type", selection: $setType) {
                        ForEach(SetType.allCases) { type in
                            Text(type.label).tag(type)
                        }
                    }
                    .pickerStyle(.segmented)
                }
            }
            .navigationTitle("Set \(set.setNumber)")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { save() }
                        .fontWeight(.semibold)
                }
                ToolbarItemGroup(placement: .keyboard) {
                    Spacer()
                    Button("Done") { focus = nil }
                }
            }
            .onAppear(perform: loadValues)
        }
    }

    private func loadValues() {
        loadText = set.loadKg == 0 ? "" : set.loadKg.clean
        repsText = set.reps == 0 ? "" : String(set.reps)
        if let rpe = set.rpe {
            effort = rpe
            hasEffort = true
        }
        setType = set.setType
    }

    private func save() {
        set.loadKg = load
        set.reps = reps
        set.rpe = hasEffort ? effort : nil
        set.rir = nil
        set.setType = setType
        // Stamped on confirmation, so the time reflects when the set actually
        // finished rather than when the row was created. DATA.md §18.
        set.completedAt = Date()
        try? context.save()
        dismiss()
    }
}

/// Typed entry with nudge buttons either side.
///
/// A stepper alone is unusable in a gym — 60 kg at 1.25 kg a tap is 48 taps.
/// Typing is the fast path; the nudges are for the common small adjustment
/// between sets.
private struct NumberField: View {
    @Binding var text: String
    let suffix: String
    let keyboard: UIKeyboardType
    let step: Double
    let placeholder: String

    var body: some View {
        HStack(spacing: 12) {
            TextField(placeholder, text: $text)
                .keyboardType(keyboard)
                .font(.title2.monospacedDigit())
                .frame(maxWidth: .infinity, alignment: .leading)

            Text(suffix)
                .font(.subheadline)
                .foregroundStyle(.secondary)

            HStack(spacing: 0) {
                nudge(-step, systemImage: "minus")
                Divider().frame(height: 22)
                nudge(step, systemImage: "plus")
            }
            .background(.quaternary, in: RoundedRectangle(cornerRadius: 8))
        }
    }

    private func nudge(_ delta: Double, systemImage: String) -> some View {
        Button {
            let current = Double(text.replacingOccurrences(of: ",", with: ".")) ?? 0
            let next = max(0, current + delta)
            text = next == 0 ? "" : next.clean
        } label: {
            Image(systemName: systemImage)
                .frame(width: 44, height: 32)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }
}
