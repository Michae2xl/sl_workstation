// Draws the app icon: the Shielded Labs shield on a black rounded square with a gradient.
// Usage: swift icon.swift <shield.png> <out.png>
import Cocoa

let arguments = CommandLine.arguments
guard arguments.count == 3, let shield = NSImage(contentsOfFile: arguments[1]) else {
    FileHandle.standardError.write("usage: swift icon.swift <shield.png> <out.png>\n".data(using: .utf8)!)
    exit(1)
}

let side = 1024
let margin: CGFloat = 100
let corner: CGFloat = 185
guard let canvas = NSBitmapImageRep(
    bitmapDataPlanes: nil, pixelsWide: side, pixelsHigh: side, bitsPerSample: 8, samplesPerPixel: 4,
    hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0),
    let context = NSGraphicsContext(bitmapImageRep: canvas)
else { exit(1) }

func gray(_ value: CGFloat, _ opacity: CGFloat = 1) -> NSColor {
    NSColor(srgbRed: value, green: value, blue: value * 1.04, alpha: opacity)
}

NSGraphicsContext.saveGraphicsState()
NSGraphicsContext.current = context
let frameRect = NSRect(x: margin, y: margin, width: CGFloat(side) - 2 * margin, height: CGFloat(side) - 2 * margin)
let shape = NSBezierPath(roundedRect: frameRect, xRadius: corner, yRadius: corner)

// Soft drop shadow under the tile, as on system icons.
NSGraphicsContext.saveGraphicsState()
let shadow = NSShadow()
shadow.shadowColor = NSColor.black.withAlphaComponent(0.45)
shadow.shadowBlurRadius = 28
shadow.shadowOffset = NSSize(width: 0, height: -12)
shadow.set()
NSColor.black.setFill()
shape.fill()
NSGraphicsContext.restoreGraphicsState()

// Background: charcoal at the top fading to black at the bottom.
NSGraphicsContext.saveGraphicsState()
shape.addClip()
NSGradient(colorsAndLocations: (gray(0.20), 0.0), (gray(0.09), 0.45), (gray(0.0), 1.0))?
    .draw(in: frameRect, angle: -90)
// A glow behind the shield lifts it off the background.
let middle = NSPoint(x: frameRect.midX, y: frameRect.midY + 30)
NSGradient(colorsAndLocations: (gray(1, 0.20), 0.0), (gray(1, 0.06), 0.55), (gray(1, 0.0), 1.0))?
    .draw(fromCenter: middle, radius: 0, toCenter: middle, radius: 430, options: [])
// A thin highlight along the top edge.
NSGradient(colorsAndLocations: (gray(1, 0.16), 0.0), (gray(1, 0.0), 0.12))?
    .draw(in: frameRect, angle: -90)
NSGraphicsContext.restoreGraphicsState()

// Hairline rim.
let rim = NSBezierPath(roundedRect: frameRect.insetBy(dx: 2, dy: 2), xRadius: corner - 2, yRadius: corner - 2)
gray(1, 0.14).setStroke()
rim.lineWidth = 4
rim.stroke()

let inset: CGFloat = 140
shield.draw(in: frameRect.insetBy(dx: inset, dy: inset), from: .zero, operation: .sourceOver, fraction: 1)
NSGraphicsContext.restoreGraphicsState()

guard let png = canvas.representation(using: .png, properties: [:]) else { exit(1) }
do {
    try png.write(to: URL(fileURLWithPath: arguments[2]))
} catch {
    FileHandle.standardError.write("could not write the icon: \(error.localizedDescription)\n".data(using: .utf8)!)
    exit(1)
}
