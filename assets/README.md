# 项目内仿真资源

`go2w_description/` 是当前 Go2W MuJoCo pipeline 所需的最小资源集：

- `mjcf/go2w_scene.xml`：默认场景，包含楼梯和 `go2w.xml` 引用；
- `mjcf/go2w.xml`：机器人 MJCF、D435i 相机和非碰撞可视化 geom；
- `meshes/*.stl`：MJCF 使用的机器人网格。

XML 中的 `meshdir="../meshes/"` 使用项目内相对路径。这里不复制 ROS/URDF/DAE
等当前 pipeline 不读取的资源，减少迁移体积和无关依赖。
