const { VuetifyPlugin } = require('webpack-plugin-vuetify');
const { defineConfig } = require("@vue/cli-service")

module.exports = defineConfig({
  publicPath: "./",
  productionSourceMap: false,

  configureWebpack: {
    plugins: [
      new VuetifyPlugin()
    ]
  },

  // Needed for testing on real phones over the LAN. This makes the dev server
  // insecure, but that's OK since we only use it in controlled circumstances.
  devServer: {
    allowedHosts: 'all',
    client: {
      overlay: false
    }
  }
});
