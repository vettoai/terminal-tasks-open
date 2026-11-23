#!/bin/sh
set -eu
curl -fsSL https://github.com/foundry-rs/foundry/releases/download/v1.3.5/foundry_v1.3.5_linux_amd64.tar.gz | tar xz -C /usr/local/bin anvil forge cast
printf '%s\n' 'a0620cf845e1cdf6fcbd209dfe07cffd3e9004f5dadda7971678c59e42eb6f40  /usr/local/bin/anvil' '2d18b688694ce3a4e973eee30fb6991789061e3c3ad1da87bcde8baa1761359f  /usr/local/bin/cast' '0439acf59828c9bdd3e594c97b2108fe27b9c267d78d3a9376bd19d9e4442213  /usr/local/bin/forge' | sha256sum -c -
curl -fsSL https://raw.githubusercontent.com/ethereum/solc-bin/gh-pages/linux-amd64/solc-linux-amd64-v0.8.24+commit.e11b9ed9 -o /usr/local/bin/solc
echo 'fb03a29a517452b9f12bcf459ef37d0a543765bb3bbc911e70a87d6a37c30d5f  /usr/local/bin/solc' | sha256sum -c -
chmod 755 /usr/local/bin/solc
mkdir -p /root/.svm/0.8.24
cp /usr/local/bin/solc /root/.svm/0.8.24/solc-0.8.24
for version in 4.9.6 5.4.0; do
    for package in contracts contracts-upgradeable; do
        destination="/build/project/lib/openzeppelin-$package-$version"
        mkdir -p "$destination"
        curl -fsSL "https://registry.npmjs.org/@openzeppelin/$package/-/$package-$version.tgz" | tar xz --strip-components=1 -C "$destination"
    done
done
