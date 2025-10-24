import Foundation
import AVFoundation

// Simple command-line snippet to extract chapter titles from an M4B file
// Usage: swift extract_chapters.swift /path/to/book.m4b

func sanitizeForUI(_ s: String) -> String {
    var out = s
    // remove control characters
    out = out.components(separatedBy: CharacterSet.controlCharacters).joined()
    // replace underscores
    out = out.replacingOccurrences(of: "_+", with: " ", options: .regularExpression)
    // collapse whitespace
    out = out.replacingOccurrences(of: "\\s+", with: " ", options: .regularExpression)
    return out.trimmingCharacters(in: .whitespacesAndNewlines)
}

let args = CommandLine.arguments
if args.count < 2 {
    print("Usage: extract_chapters.swift /path/to/book.m4b")
    exit(1)
}
let url = URL(fileURLWithPath: args[1])
let asset = AVAsset(url: url)
let groups = asset.chapterMetadataGroups(bestMatchingPreferredLanguages: nil)
for (i, g) in groups.enumerated() {
    var title = ""
    if let item = g.items.first(where: { $0.commonKey?.rawValue == "title" || ($0.identifier?.rawValue ?? "").contains("name") }) {
        if let raw = item.value as? String {
            title = sanitizeForUI(raw)
        }
    }
    print("Chapter \(i+1): \(title)")
}
