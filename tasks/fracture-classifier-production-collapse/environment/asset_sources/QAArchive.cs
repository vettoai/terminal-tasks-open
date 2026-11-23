using System;
using System.Drawing;
using System.Drawing.Imaging;

class QAArchive
{
    static void ConvertImage(string source, string destination)
    {
        using (var input = Image.FromFile(source))
        using (var bitmap = new Bitmap(input.Width, input.Height, PixelFormat.Format24bppRgb))
        using (var graphics = Graphics.FromImage(bitmap))
        using (var parameters = new EncoderParameters(1))
        {
            graphics.DrawImageUnscaled(input, 0, 0);
            parameters.Param[0] = new EncoderParameter(Encoder.Quality, 75L);
            ImageCodecInfo codec = Array.Find(ImageCodecInfo.GetImageEncoders(), item => item.MimeType == "image/jpeg");
            bitmap.Save(destination, codec, parameters);
        }
    }

    static int Main(string[] args)
    {
        try
        {
            if (args.Length == 1 && args[0] == "--batch")
            {
                string line;
                while ((line = Console.ReadLine()) != null)
                {
                    string[] paths = line.Split('\t');
                    ConvertImage(paths[0], paths[1]);
                    Console.WriteLine("OK");
                    Console.Out.Flush();
                }
                return 0;
            }
            if (args.Length != 2)
            {
                Console.WriteLine("JPEG archive conversion utility\nUsage: qa_archive <input.jpg> <output.jpg>\n       qa_archive --batch   (tab-separated input/output paths on stdin)");
                return args.Length == 1 && args[0] == "--help" ? 0 : 2;
            }
            ConvertImage(args[0], args[1]);
            return 0;
        }
        catch (Exception error)
        {
            Console.Error.WriteLine(error.Message);
            return 1;
        }
    }
}
