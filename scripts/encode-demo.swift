// Encode coordinator-captured browser PNG frames; no traffic or image synthesis.
// swift scripts/encode-demo.swift FRAME_DIRECTORY OUTPUT.mov FPS
import AppKit
import AVFoundation
import Foundation

func fail(_ message: String) -> Never { fputs(message + "\n", stderr); exit(1) }
guard CommandLine.arguments.count == 4,
      let fps = Int32(CommandLine.arguments[3]), fps > 0, fps <= 30 else {
    fail("Usage: swift scripts/encode-demo.swift FRAME_DIRECTORY OUTPUT.mov FPS (1...30)")
}
let input = URL(fileURLWithPath: CommandLine.arguments[1])
let output = URL(fileURLWithPath: CommandLine.arguments[2])
let frames = try FileManager.default.contentsOfDirectory(at: input, includingPropertiesForKeys: nil)
    .filter { $0.pathExtension.lowercased() == "png" }.sorted { $0.lastPathComponent < $1.lastPathComponent }
guard !frames.isEmpty, frames.count <= 3600 else { fail("Require 1...3600 actual captured PNG frames, ordered by padded filename") }
func load(_ url: URL) -> CGImage {
    guard let image = NSImage(contentsOf: url),
          let cg = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else { fail("Cannot decode frame") }
    return cg
}
let first = load(frames[0]), width = first.width, height = first.height
guard width > 0, height > 0, width <= 4096, height <= 4096,
      width % 2 == 0, height % 2 == 0 else { fail("Frames must have even dimensions <=4096") }
let writer = try AVAssetWriter(outputURL: output, fileType: .mov)
let track = AVAssetWriterInput(mediaType: .video, outputSettings: [
    AVVideoCodecKey: AVVideoCodecType.h264, AVVideoWidthKey: width, AVVideoHeightKey: height
])
let adaptor = AVAssetWriterInputPixelBufferAdaptor(assetWriterInput: track,
    sourcePixelBufferAttributes: [kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32ARGB,
                                 kCVPixelBufferWidthKey as String: width, kCVPixelBufferHeightKey as String: height])
guard writer.canAdd(track) else { fail("AVFoundation cannot add H.264 track") }
writer.add(track)
guard writer.startWriting() else { fail("Cannot start writer: \(String(describing: writer.error))") }
writer.startSession(atSourceTime: .zero)
for (index, frame) in frames.enumerated() {
    let image = load(frame)
    guard image.width == width && image.height == height else { fail("Frame dimensions changed") }
    let deadline = Date().addingTimeInterval(15)
    while !track.isReadyForMoreMediaData {
        if Date() > deadline || writer.status == .failed { fail("Writer stalled: \(String(describing: writer.error))") }
        Thread.sleep(forTimeInterval: 0.01)
    }
    var buffer: CVPixelBuffer?
    guard let pool = adaptor.pixelBufferPool,
          CVPixelBufferPoolCreatePixelBuffer(nil, pool, &buffer) == kCVReturnSuccess,
          let pixel = buffer else { fail("Cannot allocate frame buffer") }
    CVPixelBufferLockBaseAddress(pixel, [])
    guard let context = CGContext(data: CVPixelBufferGetBaseAddress(pixel), width: width, height: height,
                                  bitsPerComponent: 8, bytesPerRow: CVPixelBufferGetBytesPerRow(pixel),
                                  space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.noneSkipFirst.rawValue) else { fail("Cannot create frame context") }
    context.draw(image, in: CGRect(x: 0, y: 0, width: width, height: height))
    CVPixelBufferUnlockBaseAddress(pixel, [])
    guard adaptor.append(pixel, withPresentationTime: CMTime(value: Int64(index), timescale: fps)) else { fail("Cannot append captured frame") }
}
track.markAsFinished()
let done = DispatchSemaphore(value: 0)
writer.finishWriting { done.signal() }
guard done.wait(timeout: .now() + 30) == .success, writer.status == .completed else {
    fail("Video finalization failed: \(String(describing: writer.error))")
}
print("Encoded \(frames.count) real captured frames: \(output.lastPathComponent)")
