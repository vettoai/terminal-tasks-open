#include <unistd.h>
#include <stdio.h>
#include <stdlib.h>

int main(int argc, char **argv) {
    char **arguments = calloc((size_t)argc + 2, sizeof(char *));
    if (!arguments) return 1;
    arguments[0] = "/usr/bin/mono";
    arguments[1] = "/opt/legacy/QAArchive.exe";
    for (int index = 1; index < argc; index++) arguments[index + 1] = argv[index];
    execv(arguments[0], arguments);
    perror("qa_archive");
    return 1;
}
