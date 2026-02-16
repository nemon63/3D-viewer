import os

import numpy as np
from PyQt5.QtCore import QPoint, Qt
from PyQt5.QtWidgets import QOpenGLWidget
from OpenGL.GL import (
    GL_COLOR_BUFFER_BIT,
    GL_DEPTH_BUFFER_BIT,
    GL_DEPTH_TEST,
    GL_FALSE,
    GL_FLOAT,
    GL_FRAGMENT_SHADER,
    GL_LINEAR,
    GL_REPEAT,
    GL_RGB,
    GL_RGBA,
    GL_TEXTURE0,
    GL_TEXTURE1,
    GL_TEXTURE2,
    GL_TEXTURE3,
    GL_TEXTURE_2D,
    GL_TEXTURE_MAG_FILTER,
    GL_TEXTURE_MIN_FILTER,
    GL_TEXTURE_WRAP_S,
    GL_TEXTURE_WRAP_T,
    GL_TRIANGLES,
    GL_UNPACK_ALIGNMENT,
    GL_UNSIGNED_BYTE,
    GL_UNSIGNED_INT,
    GL_VERTEX_SHADER,
    glActiveTexture,
    glBindTexture,
    glClear,
    glClearColor,
    glDeleteProgram,
    glDeleteTextures,
    glDisable,
    glDisableClientState,
    glDrawElements,
    glEnable,
    glEnableClientState,
    glGenTextures,
    glGetUniformLocation,
    glLoadIdentity,
    glMatrixMode,
    glNormalPointer,
    glPixelStorei,
    glRotatef,
    glTexCoordPointer,
    glTexImage2D,
    glTexParameteri,
    glUniform1f,
    glUniform1i,
    glUniform3f,
    glUseProgram,
    glVertexPointer,
    glViewport,
    GL_MODELVIEW,
    GL_PROJECTION,
    GL_NORMAL_ARRAY,
    GL_TEXTURE_COORD_ARRAY,
    GL_VERTEX_ARRAY,
)
from OpenGL.GLU import gluLookAt, gluPerspective
from OpenGL.GL.shaders import compileProgram, compileShader

try:
    from PIL import Image
except ImportError:
    Image = None

from viewer.loaders.model_loader import load_model_payload

CHANNEL_BASE = "basecolor"
CHANNEL_METAL = "metal"
CHANNEL_ROUGH = "roughness"
CHANNEL_NORMAL = "normal"
ALL_CHANNELS = (CHANNEL_BASE, CHANNEL_METAL, CHANNEL_ROUGH, CHANNEL_NORMAL)


VERTEX_SHADER_SRC = """
#version 120
varying vec3 vPosView;
varying vec3 vNormalView;
varying vec2 vUv;

void main() {
    vec4 posView = gl_ModelViewMatrix * gl_Vertex;
    vPosView = posView.xyz;
    vNormalView = normalize(gl_NormalMatrix * gl_Normal);
    vUv = gl_MultiTexCoord0.xy;
    gl_Position = gl_ModelViewProjectionMatrix * gl_Vertex;
}
"""


FRAGMENT_SHADER_SRC = """
#version 120
varying vec3 vPosView;
varying vec3 vNormalView;
varying vec2 vUv;

uniform vec3 uLightPosView0;
uniform vec3 uLightPosView1;
uniform vec3 uLightColor0;
uniform vec3 uLightColor1;

uniform sampler2D uBaseColorTex;
uniform sampler2D uMetalTex;
uniform sampler2D uRoughTex;
uniform sampler2D uNormalTex;

uniform int uHasBase;
uniform int uHasMetal;
uniform int uHasRough;
uniform int uHasNormal;
uniform int uUnlitTexturePreview;
uniform int uUseAlphaCutout;
uniform float uAlphaCutoff;

float DistributionGGX(vec3 N, vec3 H, float roughness) {
    float a = roughness * roughness;
    float a2 = a * a;
    float NdotH = max(dot(N, H), 0.0);
    float NdotH2 = NdotH * NdotH;
    float denom = (NdotH2 * (a2 - 1.0) + 1.0);
    denom = 3.14159265 * denom * denom;
    return a2 / max(denom, 0.0001);
}

float GeometrySchlickGGX(float NdotV, float roughness) {
    float r = roughness + 1.0;
    float k = (r * r) / 8.0;
    float denom = NdotV * (1.0 - k) + k;
    return NdotV / max(denom, 0.0001);
}

float GeometrySmith(vec3 N, vec3 V, vec3 L, float roughness) {
    float NdotV = max(dot(N, V), 0.0);
    float NdotL = max(dot(N, L), 0.0);
    float ggx2 = GeometrySchlickGGX(NdotV, roughness);
    float ggx1 = GeometrySchlickGGX(NdotL, roughness);
    return ggx1 * ggx2;
}

vec3 fresnelSchlick(float cosTheta, vec3 F0) {
    return F0 + (1.0 - F0) * pow(1.0 - cosTheta, 5.0);
}

vec3 computeLight(vec3 N, vec3 V, vec3 albedo, float metallic, float roughness, vec3 F0, vec3 lightPos, vec3 lightColor) {
    vec3 L = normalize(lightPos - vPosView);
    vec3 H = normalize(V + L);
    float dist = length(lightPos - vPosView);
    float attenuation = 1.0 / max(dist * dist, 0.0001);
    vec3 radiance = lightColor * attenuation;

    float NDF = DistributionGGX(N, H, roughness);
    float G = GeometrySmith(N, V, L, roughness);
    vec3 F = fresnelSchlick(max(dot(H, V), 0.0), F0);

    vec3 numerator = NDF * G * F;
    float denom = 4.0 * max(dot(N, V), 0.0) * max(dot(N, L), 0.0) + 0.0001;
    vec3 specular = numerator / denom;

    vec3 kS = F;
    vec3 kD = (vec3(1.0) - kS) * (1.0 - metallic);
    float NdotL = max(dot(N, L), 0.0);
    return (kD * albedo / 3.14159265 + specular) * radiance * NdotL;
}

void main() {
    vec4 baseSample = (uHasBase == 1) ? texture2D(uBaseColorTex, vUv) : vec4(0.75, 0.75, 0.75, 1.0);
    vec3 base = baseSample.rgb;
    float alpha = baseSample.a;

    if (uUseAlphaCutout == 1 && alpha < uAlphaCutoff) {
        discard;
    }
    float metallic = (uHasMetal == 1) ? texture2D(uMetalTex, vUv).r : 0.0;
    float roughness = (uHasRough == 1) ? texture2D(uRoughTex, vUv).r : 0.55;
    roughness = clamp(roughness, 0.05, 1.0);
    metallic = clamp(metallic, 0.0, 1.0);

    vec3 N = normalize(vNormalView);
    if (uHasNormal == 1) {
        vec3 nMap = texture2D(uNormalTex, vUv).xyz * 2.0 - 1.0;
        // Tangent space is not available in this fixed-function bridge, so apply as soft perturbation.
        N = normalize(mix(N, normalize(vec3(nMap.xy, abs(nMap.z))), 0.35));
    }

    if (uUnlitTexturePreview == 1 && uHasBase == 1) {
        gl_FragColor = vec4(pow(base, vec3(1.0 / 2.2)), alpha);
        return;
    }

    vec3 V = normalize(-vPosView);
    vec3 F0 = mix(vec3(0.04), base, metallic);

    vec3 Lo = vec3(0.0);
    Lo += computeLight(N, V, base, metallic, roughness, F0, uLightPosView0, uLightColor0);
    Lo += computeLight(N, V, base, metallic, roughness, F0, uLightPosView1, uLightColor1);

    vec3 ambient = vec3(0.03) * base;
    vec3 color = ambient + Lo;

    // Simple filmic tonemap + gamma
    color = color / (color + vec3(1.0));
    color = pow(color, vec3(1.0 / 2.2));
    gl_FragColor = vec4(color, alpha);
}
"""


class OpenGLWidget(QOpenGLWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.angle_x = 0
        self.angle_y = 0
        self.zoom = 1.0
        self.last_mouse_pos = QPoint()

        self.vertices = np.array([], dtype=np.float32)
        self.indices = np.array([], dtype=np.uint32)
        self.normals = np.array([], dtype=np.float32)
        self.texcoords = np.array([], dtype=np.float32)

        self.shader_program = None
        self.texture_ids = {ch: 0 for ch in ALL_CHANNELS}
        self.last_texture_path = ""
        self.last_texture_paths = {ch: "" for ch in ALL_CHANNELS}
        self.base_texture_has_alpha = False
        self.last_texture_sets = {}
        self.last_debug_info = {}
        self.last_error = ""

        self.unlit_texture_preview = False
        self.light_positions = [
            [1.8, 1.2, 2.0],
            [-1.6, 1.0, 1.8],
        ]
        self.light_colors = [
            [12.0, 12.0, 12.0],
            [7.0, 7.0, 7.0],
        ]
        self.alpha_cutoff = 0.5

    def initializeGL(self):
        glEnable(GL_DEPTH_TEST)
        glClearColor(0.0, 0.0, 0.0, 1.0)
        self._init_shaders()

    def _init_shaders(self):
        self.shader_program = compileProgram(
            compileShader(VERTEX_SHADER_SRC, GL_VERTEX_SHADER),
            compileShader(FRAGMENT_SHADER_SRC, GL_FRAGMENT_SHADER),
        )

    def load_mesh(self, file_path: str) -> bool:
        try:
            self._clear_all_textures()
            payload = load_model_payload(file_path)
            self.vertices = payload.vertices
            self.indices = payload.indices
            self.normals = payload.normals
            self.texcoords = payload.texcoords
            self.last_texture_sets = payload.texture_sets or {}
            self.last_debug_info = payload.debug_info or {}
            self.last_texture_path = ""

            if self.texcoords.size > 0:
                self._apply_default_texture_set()

            if self.vertices.size == 0 or self.indices.size == 0:
                raise RuntimeError("Model does not contain valid geometry.")

            self.last_error = ""
            self.update()
            return True
        except Exception as exc:
            self.vertices = np.array([], dtype=np.float32)
            self.indices = np.array([], dtype=np.uint32)
            self.normals = np.array([], dtype=np.float32)
            self.texcoords = np.array([], dtype=np.float32)
            self.last_texture_path = ""
            self.last_texture_sets = {}
            self.last_debug_info = {}
            self.last_error = str(exc)
            self.update()
            return False

    def _apply_default_texture_set(self):
        for ch in ALL_CHANNELS:
            paths = self.last_texture_sets.get(ch, [])
            if paths:
                self.apply_texture_path(ch, paths[0])

        self.last_texture_path = self.last_texture_paths.get(CHANNEL_BASE, "")

    def resizeGL(self, w: int, h: int):
        h = max(h, 1)
        glViewport(0, 0, w, h)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        gluPerspective(45.0, w / h, 0.1, 100.0)

    def paintGL(self):
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        gluLookAt(0, 0, 3 / self.zoom, 0, 0, 0, 0, 1, 0)
        glRotatef(self.angle_x, 1, 0, 0)
        glRotatef(self.angle_y, 0, 1, 0)

        if self.vertices.size == 0 or self.indices.size == 0 or self.shader_program is None:
            return

        glUseProgram(self.shader_program)
        try:
            self._set_shader_uniforms()
            self._draw_mesh()
        finally:
            glUseProgram(0)

    def _set_shader_uniforms(self):
        self._set_sampler_uniform("uBaseColorTex", 0)
        self._set_sampler_uniform("uMetalTex", 1)
        self._set_sampler_uniform("uRoughTex", 2)
        self._set_sampler_uniform("uNormalTex", 3)

        self._bind_texture_unit(0, self.texture_ids[CHANNEL_BASE])
        self._bind_texture_unit(1, self.texture_ids[CHANNEL_METAL])
        self._bind_texture_unit(2, self.texture_ids[CHANNEL_ROUGH])
        self._bind_texture_unit(3, self.texture_ids[CHANNEL_NORMAL])

        self._set_int_uniform("uHasBase", 1 if self.texture_ids[CHANNEL_BASE] else 0)
        self._set_int_uniform("uHasMetal", 1 if self.texture_ids[CHANNEL_METAL] else 0)
        self._set_int_uniform("uHasRough", 1 if self.texture_ids[CHANNEL_ROUGH] else 0)
        self._set_int_uniform("uHasNormal", 1 if self.texture_ids[CHANNEL_NORMAL] else 0)
        self._set_int_uniform("uUnlitTexturePreview", 1 if self.unlit_texture_preview else 0)
        self._set_int_uniform("uUseAlphaCutout", 1 if self.base_texture_has_alpha else 0)
        self._set_float_uniform("uAlphaCutoff", self.alpha_cutoff)

        self._set_vec3_uniform("uLightPosView0", *self.light_positions[0])
        self._set_vec3_uniform("uLightPosView1", *self.light_positions[1])
        self._set_vec3_uniform("uLightColor0", *self.light_colors[0])
        self._set_vec3_uniform("uLightColor1", *self.light_colors[1])

    def _draw_mesh(self):
        glEnableClientState(GL_VERTEX_ARRAY)
        glVertexPointer(3, GL_FLOAT, 0, self.vertices)

        glEnableClientState(GL_NORMAL_ARRAY)
        glNormalPointer(GL_FLOAT, 0, self.normals)

        has_uv = self.texcoords.size > 0 and self.texcoords.shape[0] == self.vertices.shape[0]
        if has_uv:
            glEnableClientState(GL_TEXTURE_COORD_ARRAY)
            glTexCoordPointer(2, GL_FLOAT, 0, self.texcoords)

        glDrawElements(GL_TRIANGLES, int(self.indices.size), GL_UNSIGNED_INT, self.indices)

        if has_uv:
            glDisableClientState(GL_TEXTURE_COORD_ARRAY)
        glDisableClientState(GL_NORMAL_ARRAY)
        glDisableClientState(GL_VERTEX_ARRAY)

        # Unbind texture units
        for unit in (GL_TEXTURE0, GL_TEXTURE1, GL_TEXTURE2, GL_TEXTURE3):
            glActiveTexture(unit)
            glBindTexture(GL_TEXTURE_2D, 0)

    def _set_sampler_uniform(self, name, value):
        location = glGetUniformLocation(self.shader_program, name)
        if location != -1:
            glUniform1i(location, value)

    def _set_int_uniform(self, name, value):
        location = glGetUniformLocation(self.shader_program, name)
        if location != -1:
            glUniform1i(location, int(value))

    def _set_float_uniform(self, name, value):
        location = glGetUniformLocation(self.shader_program, name)
        if location != -1:
            glUniform1f(location, float(value))

    def _set_vec3_uniform(self, name, x, y, z):
        location = glGetUniformLocation(self.shader_program, name)
        if location != -1:
            glUniform3f(location, float(x), float(y), float(z))

    def _bind_texture_unit(self, slot: int, texture_id: int):
        active = [GL_TEXTURE0, GL_TEXTURE1, GL_TEXTURE2, GL_TEXTURE3][slot]
        glActiveTexture(active)
        glBindTexture(GL_TEXTURE_2D, int(texture_id) if texture_id else 0)

    def mousePressEvent(self, event):
        self.last_mouse_pos = event.pos()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton:
            dx = event.x() - self.last_mouse_pos.x()
            dy = event.y() - self.last_mouse_pos.y()
            self.angle_x += dy
            self.angle_y += dx
            self.last_mouse_pos = event.pos()
            self.update()

    def wheelEvent(self, event):
        delta = event.angleDelta().y() / 120
        self.zoom *= 1.1 ** delta
        self.resizeGL(self.width(), self.height())
        self.update()

    def set_angle(self, angle_x: float, angle_y: float):
        self.angle_x = angle_x
        self.angle_y = angle_y
        self.update()

    def apply_texture_path(self, channel: str, path: str) -> bool:
        if channel not in ALL_CHANNELS:
            return False
        if Image is None:
            return False
        if not path:
            self._clear_channel_texture(channel)
            self.update()
            return True
        if not os.path.isfile(path):
            return False

        try:
            with Image.open(path) as img:
                image_copy = img.copy()
                has_alpha = image_copy.mode in ("RGBA", "LA") or ("transparency" in image_copy.info)
                texture_id = self._upload_texture_image(image_copy, old_texture_id=self.texture_ids[channel])
            self.texture_ids[channel] = texture_id
            self.last_texture_paths[channel] = path
            if channel == CHANNEL_BASE:
                self.last_texture_path = path
                self.base_texture_has_alpha = has_alpha
            self.update()
            return True
        except Exception:
            return False

    def _clear_channel_texture(self, channel: str):
        tex_id = self.texture_ids.get(channel, 0)
        if tex_id:
            self._delete_texture_id(tex_id)
            self.texture_ids[channel] = 0
            self.last_texture_paths[channel] = ""
            if channel == CHANNEL_BASE:
                self.last_texture_path = ""
                self.base_texture_has_alpha = False

    def _upload_texture_image(self, image, old_texture_id=0):
        if image is None:
            raise RuntimeError("Texture image is empty.")

        if isinstance(image, np.ndarray):
            arr = image
        elif Image is not None and isinstance(image, Image.Image):
            if image.mode not in ("RGB", "RGBA"):
                image = image.convert("RGBA")
            arr = np.array(image, dtype=np.uint8)
        else:
            arr = np.array(image)

        if arr.ndim != 3:
            raise RuntimeError("Texture must be RGB/RGBA.")

        arr = np.flipud(arr)
        if arr.dtype != np.uint8:
            arr = arr.astype(np.uint8)

        channels = arr.shape[2]
        if channels == 3:
            image_format = GL_RGB
        elif channels == 4:
            image_format = GL_RGBA
        else:
            raise RuntimeError("Texture must have 3 or 4 channels.")

        self.makeCurrent()
        try:
            if old_texture_id:
                glDeleteTextures([int(old_texture_id)])

            texture_id = glGenTextures(1)
            if isinstance(texture_id, (tuple, list)):
                texture_id = int(texture_id[0])
            texture_id = int(texture_id)

            glBindTexture(GL_TEXTURE_2D, texture_id)
            glPixelStorei(GL_UNPACK_ALIGNMENT, 1)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT)
            glTexImage2D(
                GL_TEXTURE_2D,
                0,
                image_format,
                int(arr.shape[1]),
                int(arr.shape[0]),
                0,
                image_format,
                GL_UNSIGNED_BYTE,
                arr,
            )
            glBindTexture(GL_TEXTURE_2D, 0)
            return texture_id
        finally:
            self.doneCurrent()

    def _delete_texture_id(self, tex_id: int):
        if not tex_id:
            return
        if self.context() is None:
            return
        self.makeCurrent()
        try:
            glDeleteTextures([int(tex_id)])
        finally:
            self.doneCurrent()

    def _clear_all_textures(self):
        for ch in ALL_CHANNELS:
            self._clear_channel_texture(ch)
        self.last_texture_paths = {ch: "" for ch in ALL_CHANNELS}
        self.last_texture_path = ""

    def closeEvent(self, event):
        self._clear_all_textures()
        if self.shader_program:
            try:
                glDeleteProgram(self.shader_program)
            except Exception:
                pass
            self.shader_program = None
        super().closeEvent(event)
