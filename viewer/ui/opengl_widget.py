import os

import numpy as np
from PyQt5.QtCore import QPoint, Qt, QTimer
from PyQt5.QtWidgets import QOpenGLWidget
from OpenGL.GL import (
    GL_BLEND,
    GL_COLOR_BUFFER_BIT,
    GL_DEPTH_BUFFER_BIT,
    GL_DEPTH_TEST,
    GL_FALSE,
    GL_FLOAT,
    GL_ONE_MINUS_SRC_ALPHA,
    GL_FRAGMENT_SHADER,
    GL_SRC_ALPHA,
    GL_LINEAR,
    GL_REPEAT,
    GL_RGB,
    GL_RGBA,
    GL_TEXTURE0,
    GL_TEXTURE1,
    GL_TEXTURE2,
    GL_TEXTURE3,
    GL_TEXTURE4,
    GL_TEXTURE_2D,
    GL_TEXTURE_MAG_FILTER,
    GL_TEXTURE_MIN_FILTER,
    GL_TEXTURE_WRAP_S,
    GL_TEXTURE_WRAP_T,
    GL_TRIANGLES,
    GL_QUADS,
    GL_UNPACK_ALIGNMENT,
    GL_UNSIGNED_BYTE,
    GL_UNSIGNED_INT,
    GL_VERTEX_SHADER,
    GL_DEPTH_COMPONENT,
    GL_FRAMEBUFFER,
    GL_DEPTH_ATTACHMENT,
    GL_FRAMEBUFFER_COMPLETE,
    GL_NEAREST,
    GL_CLAMP_TO_EDGE,
    GL_NONE,
    GL_POLYGON_OFFSET_FILL,
    glActiveTexture,
    glBindTexture,
    glBlendFunc,
    glColor3f,
    glColor4f,
    glClear,
    glClearColor,
    glDeleteProgram,
    glDeleteTextures,
    glDisable,
    glDisableClientState,
    glDrawElements,
    glDrawBuffer,
    glEnable,
    glEnableClientState,
    glFramebufferTexture2D,
    glBindFramebuffer,
    glGenFramebuffers,
    glDeleteFramebuffers,
    glCheckFramebufferStatus,
    glGenTextures,
    glGetUniformLocation,
    glLoadIdentity,
    glMatrixMode,
    glPopMatrix,
    glPushMatrix,
    glNormalPointer,
    glPixelStorei,
    glRotatef,
    glTexCoordPointer,
    glTexImage2D,
    glTexParameteri,
    glTranslatef,
    glUniform2f,
    glUniform1f,
    glUniform1i,
    glUniform3f,
    glUniformMatrix4fv,
    glReadBuffer,
    glPolygonOffset,
    glUseProgram,
    glBegin,
    glEnd,
    glVertexPointer,
    glVertex3f,
    glViewport,
    glOrtho,
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
varying vec4 vShadowCoord;

uniform mat4 uLightVP;
uniform vec3 uModelOffset;

void main() {
    vec4 posView = gl_ModelViewMatrix * gl_Vertex;
    vPosView = posView.xyz;
    vNormalView = normalize(gl_NormalMatrix * gl_Normal);
    vUv = gl_MultiTexCoord0.xy;
    vec4 worldPos = vec4(gl_Vertex.xyz + uModelOffset, 1.0);
    vShadowCoord = uLightVP * worldPos;
    gl_Position = gl_ModelViewProjectionMatrix * gl_Vertex;
}
"""


FRAGMENT_SHADER_SRC = """
#version 120
varying vec3 vPosView;
varying vec3 vNormalView;
varying vec2 vUv;
varying vec4 vShadowCoord;

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
uniform float uAmbientStrength;
uniform int uShadowEnabled;
uniform sampler2D uShadowMap;
uniform vec2 uShadowTexelSize;

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

float computeShadow(vec3 N, vec3 L) {
    if (uShadowEnabled == 0) {
        return 1.0;
    }

    vec3 proj = vShadowCoord.xyz / max(vShadowCoord.w, 0.0001);
    vec2 uv = proj.xy * 0.5 + 0.5;
    float currentDepth = proj.z * 0.5 + 0.5;
    if (uv.x < 0.0 || uv.x > 1.0 || uv.y < 0.0 || uv.y > 1.0 || currentDepth > 1.0) {
        return 1.0;
    }

    float bias = max(0.0008, 0.0035 * (1.0 - max(dot(N, L), 0.0)));
    float shadow = 0.0;
    for (int x = -1; x <= 1; ++x) {
        for (int y = -1; y <= 1; ++y) {
            vec2 offset = vec2(float(x), float(y)) * uShadowTexelSize;
            float depthFromMap = texture2D(uShadowMap, uv + offset).r;
            shadow += (currentDepth - bias > depthFromMap) ? 1.0 : 0.0;
        }
    }
    shadow /= 9.0;
    return 1.0 - shadow;
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
    vec3 L0 = normalize(uLightPosView0 - vPosView);
    float shadowFactor = computeShadow(N, L0);

    vec3 Lo = vec3(0.0);
    Lo += computeLight(N, V, base, metallic, roughness, F0, uLightPosView0, uLightColor0) * shadowFactor;
    Lo += computeLight(N, V, base, metallic, roughness, F0, uLightPosView1, uLightColor1);

    vec3 ambient = vec3(uAmbientStrength) * base;
    vec3 color = ambient + Lo;

    // Simple filmic tonemap + gamma
    color = color / (color + vec3(1.0));
    color = pow(color, vec3(1.0 / 2.2));
    gl_FragColor = vec4(color, alpha);
}
"""

VERTEX_SHADER_DEPTH_SRC = """
#version 120
uniform mat4 uLightVP;
uniform vec3 uModelOffset;

void main() {
    vec4 worldPos = vec4(gl_Vertex.xyz + uModelOffset, 1.0);
    gl_Position = uLightVP * worldPos;
}
"""

FRAGMENT_SHADER_DEPTH_SRC = """
#version 120
void main() {
}
"""


class OpenGLWidget(QOpenGLWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.angle_x = 0
        self.angle_y = 0
        self.zoom = 1.0
        self.zoom_speed = 1.10
        self.rotate_speed = 1.0
        self.last_mouse_pos = QPoint()
        self.projection_mode = "perspective"
        self.model_radius = 1.0
        self.model_center = np.array([0.0, 0.0, 0.0], dtype=np.float32)
        self.model_translate = np.array([0.0, 0.0, 0.0], dtype=np.float32)
        self.model_target_y = 0.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self._orbit_vel_x = 0.0
        self._orbit_vel_y = 0.0
        self._inertia_damping = 0.92
        self._inertia_min_velocity = 0.01
        self._last_mouse_left_drag = False

        self.vertices = np.array([], dtype=np.float32)
        self.indices = np.array([], dtype=np.uint32)
        self.normals = np.array([], dtype=np.float32)
        self.texcoords = np.array([], dtype=np.float32)

        self.shader_program = None
        self.texture_ids = {ch: 0 for ch in ALL_CHANNELS}
        self.last_texture_path = ""
        self.last_texture_paths = {ch: "" for ch in ALL_CHANNELS}
        self.channel_overrides = {ch: None for ch in ALL_CHANNELS}
        self.texture_cache = {}
        self.texture_alpha_cache = {}
        self.base_texture_has_alpha = False
        self.last_texture_sets = {}
        self.submeshes = []
        self.last_debug_info = {}
        self.last_error = ""

        self.unlit_texture_preview = False
        self.light_positions = [
            [1.8, 1.2, 2.0],
            [-1.6, 1.0, 1.8],
        ]
        self.light_colors = [
            [1.0, 0.98, 0.95],
            [0.75, 0.8, 1.0],
        ]
        self.ambient_strength = 0.08
        self.key_light_intensity = 18.0
        self.fill_light_intensity = 10.0
        self.alpha_cutoff = 0.5
        self.enable_ground_shadow = False
        self.shadow_requested = False
        self.shadow_status_message = "off"
        self.background_brightness = 1.0
        self.shadow_size = 1024
        self.shadow_fbo = 0
        self.shadow_depth_tex = 0
        self.depth_shader_program = None
        self._light_vp = np.identity(4, dtype=np.float32)

        self._inertia_timer = QTimer(self)
        self._inertia_timer.setInterval(16)
        self._inertia_timer.timeout.connect(self._on_inertia_tick)
        self._warmup_queue = []
        self._warmup_timer = QTimer(self)
        self._warmup_timer.setSingleShot(True)
        self._warmup_timer.timeout.connect(self._warmup_next_texture)

    def initializeGL(self):
        glEnable(GL_DEPTH_TEST)
        glClearColor(0.0, 0.0, 0.0, 1.0)
        self._init_shaders()
        self.shadow_status_message = "off"
        if self.shadow_requested:
            self.set_shadows_enabled(True)

    def _init_shaders(self):
        self.shader_program = compileProgram(
            compileShader(VERTEX_SHADER_SRC, GL_VERTEX_SHADER),
            compileShader(FRAGMENT_SHADER_SRC, GL_FRAGMENT_SHADER),
        )

    def _init_shadow_pipeline(self):
        self.depth_shader_program = compileProgram(
            compileShader(VERTEX_SHADER_DEPTH_SRC, GL_VERTEX_SHADER),
            compileShader(FRAGMENT_SHADER_DEPTH_SRC, GL_FRAGMENT_SHADER),
        )
        self._recreate_shadow_targets(self.shadow_size)

    def _recreate_shadow_targets(self, size: int):
        size = int(max(256, size))
        if self.shadow_depth_tex:
            glDeleteTextures([int(self.shadow_depth_tex)])
            self.shadow_depth_tex = 0
        if self.shadow_fbo:
            glDeleteFramebuffers(1, [int(self.shadow_fbo)])
            self.shadow_fbo = 0

        tex_id = glGenTextures(1)
        if isinstance(tex_id, (tuple, list)):
            tex_id = int(tex_id[0])
        self.shadow_depth_tex = int(tex_id)

        glBindTexture(GL_TEXTURE_2D, self.shadow_depth_tex)
        glTexImage2D(
            GL_TEXTURE_2D,
            0,
            GL_DEPTH_COMPONENT,
            size,
            size,
            0,
            GL_DEPTH_COMPONENT,
            GL_FLOAT,
            None,
        )
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
        glBindTexture(GL_TEXTURE_2D, 0)

        fbo_id = glGenFramebuffers(1)
        if isinstance(fbo_id, (tuple, list)):
            fbo_id = int(fbo_id[0])
        self.shadow_fbo = int(fbo_id)
        glBindFramebuffer(GL_FRAMEBUFFER, self.shadow_fbo)
        glFramebufferTexture2D(GL_FRAMEBUFFER, GL_DEPTH_ATTACHMENT, GL_TEXTURE_2D, self.shadow_depth_tex, 0)
        glDrawBuffer(GL_NONE)
        glReadBuffer(GL_NONE)
        status = glCheckFramebufferStatus(GL_FRAMEBUFFER)
        glBindFramebuffer(GL_FRAMEBUFFER, 0)
        if status != GL_FRAMEBUFFER_COMPLETE:
            self.enable_ground_shadow = False
            self.shadow_status_message = "fbo incomplete"

    def load_mesh(self, file_path: str) -> bool:
        try:
            self._clear_all_textures()
            payload = load_model_payload(file_path)
            return self.apply_payload(payload)
        except Exception as exc:
            self.vertices = np.array([], dtype=np.float32)
            self.indices = np.array([], dtype=np.uint32)
            self.normals = np.array([], dtype=np.float32)
            self.texcoords = np.array([], dtype=np.float32)
            self.last_texture_path = ""
            self.last_texture_sets = {}
            self.submeshes = []
            self.last_debug_info = {}
            self.model_center = np.array([0.0, 0.0, 0.0], dtype=np.float32)
            self.model_translate = np.array([0.0, 0.0, 0.0], dtype=np.float32)
            self.model_target_y = 0.0
            self.last_error = str(exc)
            self.update()
            return False

    def apply_payload(self, payload) -> bool:
        try:
            self.vertices = payload.vertices
            self.indices = payload.indices
            self.normals = payload.normals
            self.texcoords = payload.texcoords
            self.last_texture_sets = payload.texture_sets or {}
            self.submeshes = payload.submeshes or []
            self.last_debug_info = payload.debug_info or {}
            self.last_texture_path = ""
            self.channel_overrides = {ch: None for ch in ALL_CHANNELS}
            self._compute_model_bounds()

            if self.texcoords.size > 0 and not self.submeshes:
                self._apply_default_texture_set()
            elif self.submeshes:
                first_base = (self.submeshes[0].get("texture_paths") or {}).get(CHANNEL_BASE, "")
                if not first_base:
                    first_base = self._get_fallback_texture_path(CHANNEL_BASE)
                self.last_texture_path = first_base or ""
                self.base_texture_has_alpha = bool(self.texture_alpha_cache.get(first_base, False))

            if self.vertices.size == 0 or self.indices.size == 0:
                raise RuntimeError("Model does not contain valid geometry.")

            self.last_error = ""
            self._start_texture_warmup()
            self.update()
            return True
        except Exception as exc:
            self.vertices = np.array([], dtype=np.float32)
            self.indices = np.array([], dtype=np.uint32)
            self.normals = np.array([], dtype=np.float32)
            self.texcoords = np.array([], dtype=np.float32)
            self.last_texture_path = ""
            self.last_texture_sets = {}
            self.submeshes = []
            self.last_debug_info = {}
            self.model_center = np.array([0.0, 0.0, 0.0], dtype=np.float32)
            self.model_translate = np.array([0.0, 0.0, 0.0], dtype=np.float32)
            self.model_target_y = 0.0
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
        w = max(w, 1)
        glViewport(0, 0, w, h)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        aspect = w / h
        if self.projection_mode == "orthographic":
            extent = max(0.35, self.model_radius * 1.25) / max(self.zoom, 0.01)
            glOrtho(-extent * aspect, extent * aspect, -extent, extent, 0.1, 100.0)
        else:
            gluPerspective(45.0, aspect, 0.1, 100.0)

    def paintGL(self):
        if self.enable_ground_shadow and self.vertices.size and self.indices.size and self.depth_shader_program and self.shadow_fbo:
            try:
                self._render_shadow_map()
            except Exception:
                # Runtime fallback for drivers with incomplete depth/FBO behavior.
                self.enable_ground_shadow = False
                self.shadow_status_message = "runtime fallback"

        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        self._draw_background_gradient()

        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        if self.projection_mode == "orthographic":
            camera_distance = max(0.3, self.model_radius * 2.2)
        else:
            camera_distance = max(0.3, (self.model_radius * 2.8) / max(self.zoom, 0.01))
        target_y = self.model_target_y + self.pan_y
        gluLookAt(self.pan_x, target_y, camera_distance, self.pan_x, target_y, 0, 0, 1, 0)
        glRotatef(self.angle_x, 1, 0, 0)
        glRotatef(self.angle_y, 0, 1, 0)

        self._draw_ground_plane()

        if self.vertices.size == 0 or self.indices.size == 0 or self.shader_program is None:
            return

        glPushMatrix()
        self._apply_model_translation()
        glUseProgram(self.shader_program)
        try:
            self._set_common_uniforms()
            if self.submeshes:
                for submesh in self.submeshes:
                    tex_ids, has_alpha = self._resolve_submesh_textures(submesh)
                    self._set_material_uniforms(tex_ids, has_alpha)
                    self._draw_mesh_indices(submesh["indices"])
            else:
                self._set_material_uniforms(self.texture_ids, self.base_texture_has_alpha)
                self._draw_mesh_indices(self.indices)
        finally:
            self._unbind_texture_units()
            glUseProgram(0)
            glPopMatrix()

    def _set_common_uniforms(self):
        self._set_sampler_uniform("uBaseColorTex", 0)
        self._set_sampler_uniform("uMetalTex", 1)
        self._set_sampler_uniform("uRoughTex", 2)
        self._set_sampler_uniform("uNormalTex", 3)
        self._set_sampler_uniform("uShadowMap", 4)
        self._set_int_uniform("uUnlitTexturePreview", 1 if self.unlit_texture_preview else 0)
        self._set_float_uniform("uAlphaCutoff", self.alpha_cutoff)
        self._set_float_uniform("uAmbientStrength", self.ambient_strength)

        self._set_vec3_uniform("uLightPosView0", *self.light_positions[0])
        self._set_vec3_uniform("uLightPosView1", *self.light_positions[1])
        key_color = [c * self.key_light_intensity for c in self.light_colors[0]]
        fill_color = [c * self.fill_light_intensity for c in self.light_colors[1]]
        self._set_vec3_uniform("uLightColor0", *key_color)
        self._set_vec3_uniform("uLightColor1", *fill_color)
        self._set_matrix_uniform("uLightVP", self._light_vp)
        self._set_vec3_uniform("uModelOffset", *self.model_translate)
        texel = 1.0 / float(max(self.shadow_size, 1))
        self._set_int_uniform("uShadowEnabled", 1 if (self.enable_ground_shadow and self.shadow_depth_tex) else 0)
        location = glGetUniformLocation(self.shader_program, "uShadowTexelSize")
        if location != -1:
            glUniform2f(location, texel, texel)
        self._bind_texture_unit(4, self.shadow_depth_tex)

    def _set_material_uniforms(self, texture_ids, has_base_alpha: bool):
        base_tex = int(texture_ids.get(CHANNEL_BASE, 0) or 0)
        metal_tex = int(texture_ids.get(CHANNEL_METAL, 0) or 0)
        rough_tex = int(texture_ids.get(CHANNEL_ROUGH, 0) or 0)
        normal_tex = int(texture_ids.get(CHANNEL_NORMAL, 0) or 0)

        self._bind_texture_unit(0, base_tex)
        self._bind_texture_unit(1, metal_tex)
        self._bind_texture_unit(2, rough_tex)
        self._bind_texture_unit(3, normal_tex)

        self._set_int_uniform("uHasBase", 1 if base_tex else 0)
        self._set_int_uniform("uHasMetal", 1 if metal_tex else 0)
        self._set_int_uniform("uHasRough", 1 if rough_tex else 0)
        self._set_int_uniform("uHasNormal", 1 if normal_tex else 0)
        self._set_int_uniform("uUseAlphaCutout", 1 if has_base_alpha else 0)

    def _draw_mesh_indices(self, draw_indices):
        draw_indices = np.asarray(draw_indices, dtype=np.uint32).reshape(-1)
        if draw_indices.size == 0:
            return
        glEnableClientState(GL_VERTEX_ARRAY)
        glVertexPointer(3, GL_FLOAT, 0, self.vertices)

        glEnableClientState(GL_NORMAL_ARRAY)
        glNormalPointer(GL_FLOAT, 0, self.normals)

        has_uv = self.texcoords.size > 0 and self.texcoords.shape[0] == self.vertices.shape[0]
        if has_uv:
            glEnableClientState(GL_TEXTURE_COORD_ARRAY)
            glTexCoordPointer(2, GL_FLOAT, 0, self.texcoords)

        glDrawElements(GL_TRIANGLES, int(draw_indices.size), GL_UNSIGNED_INT, draw_indices)

        if has_uv:
            glDisableClientState(GL_TEXTURE_COORD_ARRAY)
        glDisableClientState(GL_NORMAL_ARRAY)
        glDisableClientState(GL_VERTEX_ARRAY)

    def _unbind_texture_units(self):
        for unit in (GL_TEXTURE0, GL_TEXTURE1, GL_TEXTURE2, GL_TEXTURE3, GL_TEXTURE4):
            glActiveTexture(unit)
            glBindTexture(GL_TEXTURE_2D, 0)

    def _draw_background_gradient(self):
        # Screen-space gradient to avoid a flat black backdrop.
        glUseProgram(0)
        glDisable(GL_DEPTH_TEST)
        glDisable(GL_TEXTURE_2D)

        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glLoadIdentity()
        glOrtho(-1.0, 1.0, -1.0, 1.0, -1.0, 1.0)

        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()

        b = min(max(self.background_brightness, 0.2), 2.0)
        bottom = np.clip(np.array([0.03, 0.03, 0.05]) * b, 0.0, 1.0)
        top = np.clip(np.array([0.09, 0.11, 0.16]) * b, 0.0, 1.0)

        glBegin(GL_QUADS)
        glColor3f(float(bottom[0]), float(bottom[1]), float(bottom[2]))  # bottom
        glVertex3f(-1.0, -1.0, 0.0)
        glVertex3f(1.0, -1.0, 0.0)
        glColor3f(float(top[0]), float(top[1]), float(top[2]))  # top
        glVertex3f(1.0, 1.0, 0.0)
        glVertex3f(-1.0, 1.0, 0.0)
        glEnd()

        glPopMatrix()
        glMatrixMode(GL_PROJECTION)
        glPopMatrix()
        glMatrixMode(GL_MODELVIEW)
        glEnable(GL_DEPTH_TEST)

    def _draw_ground_plane(self):
        glUseProgram(0)
        glDisable(GL_TEXTURE_2D)
        size = max(1.6, self.model_radius * 3.0)
        ground_y = 0.0

        glBegin(GL_QUADS)
        glColor3f(0.07, 0.08, 0.10)
        glVertex3f(-size, ground_y, -size)
        glVertex3f(size, ground_y, -size)
        glColor3f(0.04, 0.05, 0.06)
        glVertex3f(size, ground_y, size)
        glVertex3f(-size, ground_y, size)
        glEnd()

    def _render_shadow_map(self):
        target = np.array([0.0, self.model_target_y, 0.0], dtype=np.float32)
        light_pos = np.array(self.light_positions[0], dtype=np.float32)
        light_view = self._look_at_matrix(light_pos, target, np.array([0.0, 1.0, 0.0], dtype=np.float32))
        extent = max(1.0, self.model_radius * 1.8)
        light_proj = self._ortho_matrix(-extent, extent, -extent, extent, 0.1, max(12.0, self.model_radius * 8.0))
        self._light_vp = np.dot(light_proj, light_view).astype(np.float32)

        glBindFramebuffer(GL_FRAMEBUFFER, self.shadow_fbo)
        status = glCheckFramebufferStatus(GL_FRAMEBUFFER)
        if status != GL_FRAMEBUFFER_COMPLETE:
            glBindFramebuffer(GL_FRAMEBUFFER, int(self.defaultFramebufferObject()))
            self.enable_ground_shadow = False
            self.shadow_status_message = "fbo incomplete"
            return
        glViewport(0, 0, self.shadow_size, self.shadow_size)
        glClear(GL_DEPTH_BUFFER_BIT)
        glEnable(GL_POLYGON_OFFSET_FILL)
        glPolygonOffset(2.0, 4.0)

        glUseProgram(self.depth_shader_program)
        try:
            self._set_matrix_uniform("uLightVP", self._light_vp, program=self.depth_shader_program)
            loc = glGetUniformLocation(self.depth_shader_program, "uModelOffset")
            if loc != -1:
                glUniform3f(loc, float(self.model_translate[0]), float(self.model_translate[1]), float(self.model_translate[2]))
            self._draw_mesh_positions_only()
        finally:
            glUseProgram(0)
            glDisable(GL_POLYGON_OFFSET_FILL)
            glBindFramebuffer(GL_FRAMEBUFFER, int(self.defaultFramebufferObject()))
            glViewport(0, 0, max(self.width(), 1), max(self.height(), 1))

    def _apply_model_translation(self):
        glTranslatef(
            float(self.model_translate[0]),
            float(self.model_translate[1]),
            float(self.model_translate[2]),
        )

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

    def _set_matrix_uniform(self, name, mat4, program=None):
        prog = self.shader_program if program is None else program
        location = glGetUniformLocation(prog, name)
        if location != -1:
            glUniformMatrix4fv(location, 1, GL_FALSE, np.asarray(mat4, dtype=np.float32).T)

    def _set_vec3_uniform(self, name, x, y, z):
        location = glGetUniformLocation(self.shader_program, name)
        if location != -1:
            glUniform3f(location, float(x), float(y), float(z))

    def _bind_texture_unit(self, slot: int, texture_id: int):
        active = [GL_TEXTURE0, GL_TEXTURE1, GL_TEXTURE2, GL_TEXTURE3, GL_TEXTURE4][slot]
        glActiveTexture(active)
        glBindTexture(GL_TEXTURE_2D, int(texture_id) if texture_id else 0)

    def _resolve_submesh_textures(self, submesh):
        texture_paths = submesh.get("texture_paths") or {}
        resolved = {}
        for ch in ALL_CHANNELS:
            override = self.channel_overrides.get(ch)
            if override is not None:
                resolved[ch] = override
                continue
            path = texture_paths.get(ch) or self.last_texture_paths.get(ch) or self._get_fallback_texture_path(ch)
            resolved[ch] = path or ""

        texture_ids = {ch: self._get_or_create_texture_id(resolved[ch]) for ch in ALL_CHANNELS}
        base_path = resolved.get(CHANNEL_BASE, "")
        has_alpha = bool(self.texture_alpha_cache.get(base_path, False))
        return texture_ids, has_alpha

    def _get_fallback_texture_path(self, channel: str):
        direct = self.last_texture_paths.get(channel) or ""
        if direct:
            return direct
        candidates = self.last_texture_sets.get(channel) or []
        if candidates:
            return candidates[0]
        return ""

    def _get_or_create_texture_id(self, path: str):
        if not path:
            return 0
        if path in self.texture_cache:
            return int(self.texture_cache[path])
        if Image is None or not os.path.isfile(path):
            return 0
        try:
            with Image.open(path) as img:
                image_copy = img.copy()
                has_alpha = image_copy.mode in ("RGBA", "LA") or ("transparency" in image_copy.info)
                texture_id = self._upload_texture_image(image_copy, old_texture_id=0, manage_context=False)
            self.texture_cache[path] = int(texture_id)
            self.texture_alpha_cache[path] = bool(has_alpha)
            return int(texture_id)
        except Exception:
            return 0

    def _start_texture_warmup(self):
        # Perceived performance: show model with base map first, then warm non-base maps incrementally.
        pending = []
        seen = set()
        for sub in self.submeshes:
            paths = sub.get("texture_paths") or {}
            for ch in (CHANNEL_METAL, CHANNEL_ROUGH, CHANNEL_NORMAL):
                p = paths.get(ch) or self.last_texture_paths.get(ch) or ""
                if not p:
                    candidates = self.last_texture_sets.get(ch) or []
                    p = candidates[0] if candidates else ""
                if not p:
                    continue
                key = os.path.normcase(os.path.normpath(p))
                if key in seen:
                    continue
                seen.add(key)
                pending.append(p)

        self._warmup_queue = pending
        if self._warmup_queue:
            self._warmup_timer.start(0)

    def _warmup_next_texture(self):
        if not self._warmup_queue:
            return
        path = self._warmup_queue.pop(0)
        self._get_or_create_texture_id(path)
        if self._warmup_queue:
            self._warmup_timer.start(0)

    def _draw_mesh_positions_only(self):
        glEnableClientState(GL_VERTEX_ARRAY)
        glVertexPointer(3, GL_FLOAT, 0, self.vertices)
        glDrawElements(GL_TRIANGLES, int(self.indices.size), GL_UNSIGNED_INT, self.indices)
        glDisableClientState(GL_VERTEX_ARRAY)

    def _look_at_matrix(self, eye, target, up):
        f = target - eye
        fn = np.linalg.norm(f)
        if fn < 1e-6:
            f = np.array([0.0, -1.0, 0.0], dtype=np.float32)
        else:
            f = f / fn
        u = up / max(np.linalg.norm(up), 1e-6)
        s = np.cross(f, u)
        sn = np.linalg.norm(s)
        if sn < 1e-6:
            s = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        else:
            s = s / sn
        u = np.cross(s, f)

        m = np.identity(4, dtype=np.float32)
        m[0, 0:3] = s
        m[1, 0:3] = u
        m[2, 0:3] = -f
        m[0, 3] = -np.dot(s, eye)
        m[1, 3] = -np.dot(u, eye)
        m[2, 3] = np.dot(f, eye)
        return m

    def _ortho_matrix(self, left, right, bottom, top, near, far):
        m = np.identity(4, dtype=np.float32)
        m[0, 0] = 2.0 / max(right - left, 1e-6)
        m[1, 1] = 2.0 / max(top - bottom, 1e-6)
        m[2, 2] = -2.0 / max(far - near, 1e-6)
        m[0, 3] = -(right + left) / max(right - left, 1e-6)
        m[1, 3] = -(top + bottom) / max(top - bottom, 1e-6)
        m[2, 3] = -(far + near) / max(far - near, 1e-6)
        return m

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._inertia_timer.stop()
            self._orbit_vel_x = 0.0
            self._orbit_vel_y = 0.0
            self._last_mouse_left_drag = True
        self.last_mouse_pos = event.pos()

    def mouseMoveEvent(self, event):
        accel = 2.5 if (event.modifiers() & Qt.ShiftModifier) else 1.0
        if event.buttons() == Qt.LeftButton:
            dx = event.x() - self.last_mouse_pos.x()
            dy = event.y() - self.last_mouse_pos.y()
            rot_scale = self.rotate_speed * accel
            self.angle_x += dy * rot_scale
            self.angle_y += dx * rot_scale
            self._orbit_vel_x = dx * rot_scale * 0.12
            self._orbit_vel_y = dy * rot_scale * 0.12
            self.last_mouse_pos = event.pos()
            self.update()
            return

        if event.buttons() == Qt.RightButton:
            dx = event.x() - self.last_mouse_pos.x()
            dy = event.y() - self.last_mouse_pos.y()
            pan_scale = (self.model_radius * 1.3) / max(min(self.width(), self.height()), 1)
            pan_scale /= max(self.zoom, 0.05)
            pan_scale *= accel
            self.pan_x -= dx * pan_scale
            self.pan_y += dy * pan_scale
            self.last_mouse_pos = event.pos()
            self.update()
            return

    def wheelEvent(self, event):
        accel = 1.5 if (event.modifiers() & Qt.ShiftModifier) else 1.0
        delta = event.angleDelta().y() / 120
        self.zoom *= (self.zoom_speed ** accel) ** delta
        self.zoom = min(max(self.zoom, 0.1), 20.0)
        self.resizeGL(self.width(), self.height())
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._last_mouse_left_drag:
            speed = abs(self._orbit_vel_x) + abs(self._orbit_vel_y)
            if speed > self._inertia_min_velocity:
                self._inertia_timer.start()
            self._last_mouse_left_drag = False
        super().mouseReleaseEvent(event)

    def set_angle(self, angle_x: float, angle_y: float):
        self.angle_x = angle_x
        self.angle_y = angle_y
        self.update()

    def fit_model(self):
        self.zoom = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self._request_projection_refresh()
        self.update()

    def reset_view(self):
        self.angle_x = 0.0
        self.angle_y = 0.0
        self.zoom = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.projection_mode = "perspective"
        self._inertia_timer.stop()
        self._orbit_vel_x = 0.0
        self._orbit_vel_y = 0.0
        self._request_projection_refresh()
        self.update()

    def set_projection_mode(self, mode: str):
        if mode not in ("perspective", "orthographic"):
            return
        self.projection_mode = mode
        self._request_projection_refresh()
        self.update()

    def toggle_projection_mode(self):
        self.set_projection_mode("orthographic" if self.projection_mode == "perspective" else "perspective")

    def set_zoom_speed(self, value: float):
        self.zoom_speed = min(max(value, 1.01), 1.5)

    def set_rotate_speed(self, value: float):
        self.rotate_speed = min(max(value, 0.1), 4.0)

    def set_ambient_strength(self, value: float):
        self.ambient_strength = min(max(value, 0.0), 0.5)
        self.update()

    def set_key_light_intensity(self, value: float):
        self.key_light_intensity = min(max(value, 0.0), 50.0)
        self.update()

    def set_fill_light_intensity(self, value: float):
        self.fill_light_intensity = min(max(value, 0.0), 50.0)
        self.update()

    def set_background_brightness(self, value: float):
        self.background_brightness = min(max(value, 0.2), 2.0)
        self.update()

    def set_shadows_enabled(self, enabled: bool):
        self.shadow_requested = bool(enabled)
        if not enabled:
            self.enable_ground_shadow = False
            self.shadow_status_message = "off"
            self.update()
            return False

        if self.context() is None:
            self.enable_ground_shadow = False
            self.shadow_status_message = "no context"
            return False

        self.makeCurrent()
        try:
            try:
                if self.depth_shader_program is None or self.shadow_fbo == 0 or self.shadow_depth_tex == 0:
                    self._init_shadow_pipeline()
                if self.depth_shader_program is None or self.shadow_fbo == 0 or self.shadow_depth_tex == 0:
                    self.enable_ground_shadow = False
                    self.shadow_status_message = "init failed"
                    return False
                self.enable_ground_shadow = True
                self.shadow_status_message = "on"
                return True
            except Exception:
                self.enable_ground_shadow = False
                self.shadow_status_message = "unsupported"
                return False
        finally:
            self.doneCurrent()
            self.update()

    def set_alpha_cutoff(self, value: float):
        self.alpha_cutoff = min(max(value, 0.0), 1.0)
        self.update()

    def _request_projection_refresh(self):
        # During app startup the GL context may not exist yet.
        if self.context() is None:
            return
        self.resizeGL(self.width(), self.height())

    def _on_inertia_tick(self):
        self.angle_y += self._orbit_vel_x
        self.angle_x += self._orbit_vel_y
        self._orbit_vel_x *= self._inertia_damping
        self._orbit_vel_y *= self._inertia_damping
        if abs(self._orbit_vel_x) + abs(self._orbit_vel_y) < self._inertia_min_velocity:
            self._inertia_timer.stop()
            self._orbit_vel_x = 0.0
            self._orbit_vel_y = 0.0
        self.update()

    def apply_texture_path(self, channel: str, path: str) -> bool:
        if channel not in ALL_CHANNELS:
            return False
        if Image is None:
            return False
        if not path:
            self.channel_overrides[channel] = ""
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
            self.channel_overrides[channel] = path
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

    def _upload_texture_image(self, image, old_texture_id=0, manage_context=True):
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

        if manage_context:
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
            if manage_context:
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
        self._warmup_timer.stop()
        self._warmup_queue = []
        for ch in ALL_CHANNELS:
            self._clear_channel_texture(ch)
        if self.context() is not None:
            self.makeCurrent()
            try:
                for tex_id in self.texture_cache.values():
                    if tex_id:
                        glDeleteTextures([int(tex_id)])
            finally:
                self.doneCurrent()
        self.texture_cache = {}
        self.texture_alpha_cache = {}
        self.last_texture_paths = {ch: "" for ch in ALL_CHANNELS}
        self.last_texture_path = ""

    def _compute_model_bounds(self):
        if self.vertices.size == 0:
            self.model_center = np.array([0.0, 0.0, 0.0], dtype=np.float32)
            self.model_translate = np.array([0.0, 0.0, 0.0], dtype=np.float32)
            self.model_target_y = 0.0
            self.model_radius = 1.0
            return

        mins = np.min(self.vertices, axis=0)
        maxs = np.max(self.vertices, axis=0)
        center = (mins + maxs) * 0.5
        self.model_center = center.astype(np.float32)
        self.model_translate = np.array([-center[0], -mins[1], -center[2]], dtype=np.float32)
        self.model_target_y = float(center[1] - mins[1])

        centered = self.vertices - center
        lengths = np.linalg.norm(centered, axis=1)
        if lengths.size == 0:
            self.model_radius = 1.0
            return
        radius = float(np.max(lengths))
        self.model_radius = radius if radius > 0 else 1.0

    def closeEvent(self, event):
        self._clear_all_textures()
        if self.context() is not None:
            self.makeCurrent()
            try:
                if self.shadow_depth_tex:
                    glDeleteTextures([int(self.shadow_depth_tex)])
                    self.shadow_depth_tex = 0
                if self.shadow_fbo:
                    glDeleteFramebuffers(1, [int(self.shadow_fbo)])
                    self.shadow_fbo = 0
            finally:
                self.doneCurrent()
        if self.shader_program:
            try:
                glDeleteProgram(self.shader_program)
            except Exception:
                pass
            self.shader_program = None
        if self.depth_shader_program:
            try:
                glDeleteProgram(self.depth_shader_program)
            except Exception:
                pass
            self.depth_shader_program = None
        super().closeEvent(event)
