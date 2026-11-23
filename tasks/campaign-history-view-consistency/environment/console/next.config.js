module.exports = {
  reactStrictMode: false, experimental: { cpus: 2 },
  async rewrites() {
    return [{ source: '/api/:path*', destination: 'http://127.0.0.1:3100/api/:path*' }];
  }
};
