import SwiftUI

struct ExercisePickerView: View {
    let onPick: (LibraryExercise) -> Void

    @Environment(\.dismiss) private var dismiss
    @StateObject private var library = ExerciseLibrary.shared
    @State private var query = ""

    private var results: [LibraryExercise] {
        library.search(query)
    }

    var body: some View {
        NavigationStack {
            List(results) { exercise in
                Button {
                    onPick(exercise)
                    dismiss()
                } label: {
                    VStack(alignment: .leading, spacing: 3) {
                        Text(exercise.name)
                            .font(.body)
                        HStack(spacing: 6) {
                            Text(exercise.equipment)
                                .font(.caption2)
                                .padding(.horizontal, 5)
                                .padding(.vertical, 2)
                                .background(.quaternary, in: Capsule())
                            Text(exercise.muscleSummary)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                                .lineLimit(1)
                        }
                    }
                }
                .buttonStyle(.plain)
            }
            .listStyle(.plain)
            .searchable(text: $query, prompt: "Search \(library.exercises.count) exercises")
            .navigationTitle("Add exercise")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
            }
        }
    }
}
