import com.android.zipflinger.Source;
import com.android.zipflinger.ZipArchive;
import com.android.zipflinger.ZipSource;
import java.nio.file.Files;
import java.nio.file.Path;

public class ApplyDelta {
    public static void main(String[] arguments) throws Exception {
        try (ZipArchive archive = new ZipArchive(Path.of(arguments[0]))) {
            for (String line : Files.readAllLines(Path.of(arguments[2]))) {
                String[] fields = line.split(" ", 3);
                if (fields[0].equals("delete")) {
                    archive.delete(fields[1]);
                } else {
                    ZipSource source = new ZipSource(Path.of(arguments[1]));
                    source.select(fields[2], fields[2], ZipSource.COMPRESSION_NO_CHANGE,
                            Long.parseLong(fields[1]));
                    archive.add(source);
                }
            }
        }
    }
}
