package com.practice.backend.controller;

import com.practice.backend.model.UserInfo;
import com.practice.backend.repository.UserInfoRepository;
import org.springframework.http.HttpStatus;
import org.springframework.util.StringUtils;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import java.time.LocalDateTime;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;

@RestController
@RequestMapping("/api/auth")
public class AuthController {

    private static final Set<String> ROLES = Set.of("APPLICANT", "REVIEWER", "ADMIN");
    private static final Set<String> USER_TYPES = Set.of("PERSONAL", "ENTERPRISE");
    private static final int MAX_FAILED_LOGIN = 5;
    private static final Pattern PHONE_PATTERN = Pattern.compile("^1[3-9]\\d{9}$");
    private static final Pattern EMAIL_PATTERN = Pattern.compile("^[A-Za-z0-9+_.-]+@[A-Za-z0-9.-]+$");
    private static final Pattern ID_CARD_PATTERN = Pattern.compile("^[1-9]\\d{5}(18|19|20)\\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\\d|3[01])\\d{3}[0-9Xx]$");
    private static final Pattern CREDIT_CODE_PATTERN = Pattern.compile("^[0-9A-Z]{18}$");




    private final UserInfoRepository userRepository;

    public AuthController(UserInfoRepository userRepository) {
        this.userRepository = userRepository;
    }

    @PostMapping("/register")
    public Map<String, Object> register(@RequestBody Map<String, String> body) {
        String role = body.getOrDefault("role", "APPLICANT").trim().toUpperCase();
        if (!"APPLICANT".equals(role)) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN, "审核员和管理员账号必须由管理员创建");
        }

        UserInfo user = buildUser(body, role, "PENDING_ACTIVATION");
        return toSession(userRepository.save(user));
    }

    @PostMapping("/admin/users")
    public Map<String, Object> createUserByAdmin(
            @RequestHeader(value = "X-Role", required = false) String currentRole,
            @RequestBody Map<String, String> body) {
        requireAdmin(currentRole);
        String role = body.getOrDefault("role", "").trim().toUpperCase();
        if (!ROLES.contains(role)) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "角色类型不正确");
        }
        UserInfo user = buildUser(body, role, "ACTIVE");
        user.setTwoFactorEnabled("ADMIN".equals(role));
        return toSession(userRepository.save(user));
    }

    @PostMapping("/admin/users/{id}/activate")
    public Map<String, Object> activateUser(
            @RequestHeader(value = "X-Role", required = false) String currentRole,
            @PathVariable Long id) {
        requireAdmin(currentRole);
        UserInfo user = userRepository.findById(id)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "用户不存在"));
        user.setAccountStatus("ACTIVE");
        return toSession(userRepository.save(user));
    }

    @PutMapping("/admin/users/{id}/role")
    public Map<String, Object> updateUserRole(
            @RequestHeader(value = "X-Role", required = false) String currentRole,
            @RequestHeader(value = "X-User-Id", required = false) Long currentUserId,
            @PathVariable Long id,
            @RequestBody Map<String, String> body) {
        requireAdmin(currentRole);
        String newRole = body.getOrDefault("role", "").trim().toUpperCase();
        if (!ROLES.contains(newRole)) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "角色类型不正确");
        }
        if (currentUserId != null && currentUserId.equals(id) && !"ADMIN".equals(newRole)) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "当前管理员不能取消自己的管理员权限");
        }

        UserInfo user = userRepository.findById(id)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "用户不存在"));
        user.setRole(newRole);
        user.setTwoFactorEnabled("ADMIN".equals(newRole));
        return toSession(userRepository.save(user));
    }

    @GetMapping("/admin/users")
    public List<Map<String, Object>> users(@RequestHeader(value = "X-Role", required = false) String currentRole) {
        requireAdmin(currentRole);
        return userRepository.findAll().stream().map(this::toSafeUser).toList();
    }

    @PostMapping("/login")
    public Map<String, Object> login(@RequestBody Map<String, String> body) {
        UserInfo user = userRepository.findByUsername(body.getOrDefault("username", "").trim())
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.UNAUTHORIZED, "用户名或密码错误"));
        normalizeLegacyUser(user);

        LocalDateTime now = LocalDateTime.now();
        if (user.getLockedUntil() != null && user.getLockedUntil().isAfter(now)) {
            throw new ResponseStatusException(HttpStatus.LOCKED, "账号已被锁定，请稍后再试");
        }
        if (!"ACTIVE".equals(user.getAccountStatus())) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN, "账号尚未激活");
        }
        if (!user.getPassword().equals(body.getOrDefault("password", ""))) {
            int failedCount = user.getFailedLoginCount() == null ? 1 : user.getFailedLoginCount() + 1;
            user.setFailedLoginCount(failedCount);
            if (failedCount >= MAX_FAILED_LOGIN) {
                user.setLockedUntil(now.plusMinutes(15));
            }
            userRepository.save(user);
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED, "用户名或密码错误");
        }

        user.setFailedLoginCount(0);
        user.setLockedUntil(null);
        userRepository.save(user);
        return toSession(user);
    }

    private UserInfo buildUser(Map<String, String> body, String role, String accountStatus) {
        String username = required(body, "username", "用户名不能为空");
        String password = required(body, "password", "密码不能为空");
        String displayName = required(body, "displayName", "真实姓名或企业名称不能为空");
        String identityNo = required(body, "identityNo", "身份证号不能为空").toUpperCase();
        String userType = body.getOrDefault("userType", "PERSONAL").trim().toUpperCase();
        String creditCode = body.getOrDefault("creditCode", "").trim().toUpperCase();
        String phone = required(body, "phone", "手机号不能为空");
        String email = required(body, "email", "邮箱不能为空").toLowerCase();

        if (!ROLES.contains(role)) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "角色类型不正确");
        }
        if (!USER_TYPES.contains(userType)) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "账号类型不正确");
        }
        if (!isStrongPassword(password)) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "密码至少8位，并且需要包含大写字母、小写字母、数字、特殊字符中的三类");
        }
        if (!isValidIdCard(identityNo)) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "身份证号格式或校验码不正确");
        }
        if (!PHONE_PATTERN.matcher(phone).matches()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "手机号格式不正确");
        }
        if (!EMAIL_PATTERN.matcher(email).matches()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "邮箱格式不正确");
        }
        if ("ENTERPRISE".equals(userType) && !CREDIT_CODE_PATTERN.matcher(creditCode).matches()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "企业账号必须填写18位统一社会信用代码");
        }
        if (userRepository.findByUsername(username).isPresent()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "用户名已存在");
        }
        if (userRepository.existsByIdentityNo(identityNo)) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "该身份证号已注册");
        }
        if (StringUtils.hasText(creditCode) && userRepository.existsByCreditCode(creditCode)) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "该统一社会信用代码已注册");
        }
        if (userRepository.existsByPhone(phone)) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "该手机号已注册");
        }
        if (userRepository.existsByEmail(email)) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "该邮箱已注册");
        }

        UserInfo user = new UserInfo();
        user.setUsername(username);
        user.setPassword(password);
        user.setRole(role);
        user.setDisplayName(displayName);
        user.setIdentityNo(identityNo);
        user.setUserType(userType);
        user.setCreditCode(creditCode);
        user.setPhone(phone);
        user.setEmail(email);
        user.setAccountStatus(accountStatus);
        user.setFailedLoginCount(0);
        user.setTwoFactorEnabled("ADMIN".equals(role));
        user.setCreatedAt(LocalDateTime.now());
        return user;
    }

    private boolean isStrongPassword(String password) {
        if (password.length() < 8) {
            return false;
        }
        int categories = 0;
        if (password.matches(".*[A-Z].*")) categories++;
        if (password.matches(".*[a-z].*")) categories++;
        if (password.matches(".*\\d.*")) categories++;
        if (password.matches(".*[^A-Za-z0-9].*")) categories++;
        return categories >= 3;
    }

    private boolean isValidIdCard(String identityNo) {
        if (!ID_CARD_PATTERN.matcher(identityNo).matches()) {
            return false;
        }
        String birthDate = identityNo.substring(6, 14);
        try {
            LocalDate.parse(birthDate, DateTimeFormatter.BASIC_ISO_DATE);
        } catch (DateTimeParseException ex) {
            return false;
        }

        int[] weights = {7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2};
        char[] checkCodes = {'1', '0', 'X', '9', '8', '7', '6', '5', '4', '3', '2'};
        int sum = 0;
        for (int i = 0; i < 17; i++) {
            sum += (identityNo.charAt(i) - '0') * weights[i];
        }
        return checkCodes[sum % 11] == Character.toUpperCase(identityNo.charAt(17));
    }

    private String required(Map<String, String> body, String key, String message) {
        String value = body.getOrDefault(key, "").trim();
        if (!StringUtils.hasText(value)) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, message);
        }
        return value;
    }

    private void requireAdmin(String role) {
        if (!"ADMIN".equals(role)) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN, "需要管理员权限");
        }
    }

    private void normalizeLegacyUser(UserInfo user) {
        boolean changed = false;
        if (!StringUtils.hasText(user.getAccountStatus())) {
            user.setAccountStatus("ACTIVE");
            changed = true;
        }
        if (user.getFailedLoginCount() == null) {
            user.setFailedLoginCount(0);
            changed = true;
        }
        if (user.getTwoFactorEnabled() == null) {
            user.setTwoFactorEnabled("ADMIN".equals(user.getRole()));
            changed = true;
        }
        if (!StringUtils.hasText(user.getUserType())) {
            user.setUserType("PERSONAL");
            changed = true;
        }
        if (changed) {
            userRepository.save(user);
        }
    }

    private Map<String, Object> toSession(UserInfo user) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("id", user.getId());
        result.put("username", user.getUsername());
        result.put("displayName", user.getDisplayName() == null ? user.getUsername() : user.getDisplayName());
        result.put("identityNo", user.getIdentityNo() == null ? "" : user.getIdentityNo());
        result.put("userType", user.getUserType() == null ? "PERSONAL" : user.getUserType());
        result.put("creditCode", user.getCreditCode() == null ? "" : user.getCreditCode());
        result.put("phone", user.getPhone() == null ? "" : user.getPhone());
        result.put("email", user.getEmail() == null ? "" : user.getEmail());
        result.put("role", user.getRole());
        result.put("accountStatus", user.getAccountStatus());
        result.put("twoFactorEnabled", Boolean.TRUE.equals(user.getTwoFactorEnabled()));
        result.put("token", user.getId() + ":" + user.getRole());
        return result;
    }

    private Map<String, Object> toSafeUser(UserInfo user) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("id", user.getId());
        result.put("username", user.getUsername());
        result.put("displayName", user.getDisplayName() == null ? user.getUsername() : user.getDisplayName());
        result.put("identityNo", user.getIdentityNo() == null ? "" : user.getIdentityNo());
        result.put("userType", user.getUserType() == null ? "PERSONAL" : user.getUserType());
        result.put("creditCode", user.getCreditCode() == null ? "" : user.getCreditCode());
        result.put("phone", user.getPhone() == null ? "" : user.getPhone());
        result.put("email", user.getEmail() == null ? "" : user.getEmail());
        result.put("role", user.getRole());
        result.put("accountStatus", user.getAccountStatus());
        result.put("createdAt", user.getCreatedAt());
        return result;
    }
}
