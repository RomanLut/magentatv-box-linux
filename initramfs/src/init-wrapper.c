#include <unistd.h>

int main(void) {
    char *const envp[] = {
        "HOME=/", "TERM=linux", "PATH=/bin", NULL
    };
    char *const argv[] = {"/bin/sh", "/init-script", NULL};
    execve(argv[0], argv, envp);
    _exit(127);
}
