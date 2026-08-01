module.exports = {
  packagerConfig: {
    name: 'AI小说工厂',
    executableName: 'ai-novel-factory',
    icon: './assets/icon',
    extraResource: [
      './backend',
    ],
  },
  makers: [
    {
      name: '@electron-forge/maker-squirrel',
      config: {
        name: 'ai_novel_factory',
        setupIcon: './assets/icon.ico',
      },
    },
    {
      name: '@electron-forge/maker-zip',
      platforms: ['win32', 'darwin'],
    },
  ],
  plugins: [
    {
      name: '@electron-forge/plugin-auto-unpack-natives',
      config: {},
    },
  ],
}
