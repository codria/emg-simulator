// dump_ref.cpp — emit reference FK/IK results from the C++ arm.cpp so the numpy
// port in emg_sim/kinematics/arm.py can be verified against it.
//
// Compiled against the *unmodified* KinectArmSimulator arm.cpp + GLM headers.
// Emits ref_cases.json to stdout: for each FK case the joint-frame origins and
// tip; for each IK case the target/initial-q/options and the solved q.
//
// Build: see build_and_dump.sh (needs g++ + the KinectArmSimulator repo path).

#include "arm.h"

#include <cstdio>
#include <vector>

using arm::Manipulator;
using arm::makeStandardArm;
// IKOptions is nested in Manipulator (arm::Manipulator::IKOptions).
using IKOptions = arm::Manipulator::IKOptions;

static void pvec3(const glm::vec3& v) {
    printf("[%.10g, %.10g, %.10g]", v.x, v.y, v.z);
}

static void pqvec(const std::vector<float>& q) {
    printf("[");
    for (size_t i = 0; i < q.size(); ++i)
        printf("%.10g%s", q[i], (i + 1 < q.size()) ? ", " : "");
    printf("]");
}

static void popts(const IKOptions& o) {
    printf("{");
    printf("\"max_iter\": %d, ", o.max_iter);
    printf("\"tol\": %.10g, ", o.tol);
    printf("\"lambda_\": %.10g, ", o.lambda);
    printf("\"elbow_up\": %s, ", o.elbow_up ? "true" : "false");
    printf("\"elbow_target\": %.10g, ", o.elbow_target);
    printf("\"elbow_gain\": %.10g, ", o.elbow_gain);
    printf("\"max_step\": %.10g, ", o.max_step);
    printf("\"lambda_max\": %.10g, ", o.lambda_max);
    printf("\"det_thresh\": %.10g, ", o.det_thresh);
    printf("\"dq_max\": %.10g, ", o.dq_max);
    printf("\"j4_down\": %s, ", o.j4_down ? "true" : "false");
    printf("\"j4_down_gain\": %.10g, ", o.j4_down_gain);
    printf("\"j5_down\": %s, ", o.j5_down ? "true" : "false");
    printf("\"j5_down_gain\": %.10g, ", o.j5_down_gain);
    printf("\"j1_preferred\": %s, ", o.j1_preferred ? "true" : "false");
    printf("\"j1_preferred_gain\": %.10g, ", o.j1_preferred_gain);
    printf("\"j1_target\": %.10g", o.j1_target);
    printf("}");
}

int main() {
    // ---- FK cases: fixed joint-angle vectors -----------------------------
    std::vector<std::vector<float>> fk_qs = {
        {0.f, 0.f, 0.f, 0.f, 0.f, 0.f},
        {0.3f, -0.5f, 0.8f, 0.2f, -0.4f, 0.6f},
        {1.0f, 0.7f, 1.2f, -0.9f, 0.5f, -1.1f},
        {-0.5f, 0.9f, 0.3f, 1.5f, -0.7f, 0.2f},
        {2.0f, -1.2f, 2.5f, 3.0f, 1.1f, -2.4f},
        {0.f, 1.5707963f, 0.f, 0.f, 0.f, 0.f},
    };

    printf("{\n");
    printf("\"fk_cases\": [\n");
    for (size_t c = 0; c < fk_qs.size(); ++c) {
        Manipulator m = makeStandardArm();
        m.setQ(fk_qs[c]);
        auto Ts = m.forwardKinematics();
        printf("  {\"q\": ");
        pqvec(m.q());
        printf(", \"frame_origins\": [");
        for (size_t i = 0; i < Ts.size(); ++i) {
            glm::vec3 p(Ts[i][3]);
            pvec3(p);
            printf("%s", (i + 1 < Ts.size()) ? ", " : "");
        }
        printf("], \"tip\": ");
        pvec3(m.tipPosition());
        printf("}%s\n", (c + 1 < fk_qs.size()) ? "," : "");
    }
    printf("],\n");

    // ---- IK cases: target, initial q, options ----------------------------
    struct IKCase {
        glm::vec3          target;
        std::vector<float> q0;
        IKOptions          opts;
    };

    IKOptions def;                 // library defaults (elbow_up on)
    IKOptions j1p = def; j1p.j1_preferred = true; j1p.j1_target = 0.5f;
    IKOptions j45 = def; j45.j4_down = true; j45.j5_down = true;

    std::vector<IKCase> ik_cases = {
        {{0.20f, 0.10f, 0.50f}, {0, 0, 0, 0, 0, 0}, def},
        {{0.00f, 0.30f, 0.50f}, {0, 0, 0, 0, 0, 0}, def},
        {{-0.20f, 0.20f, 0.40f}, {0, 0, 0, 0, 0, 0}, def},
        {{0.30f, -0.10f, 0.35f}, {0, 0, 0, 0, 0, 0}, def},
        {{0.15f, 0.15f, 0.55f}, {0.1f, 0.2f, 0.5f, 0.0f, 0.0f, 0.0f}, def},
        {{0.25f, 0.00f, 0.45f}, {0, 0, 0, 0, 0, 0}, j1p},
        {{0.10f, -0.25f, 0.40f}, {0, 0, 0, 0, 0, 0}, j45},
    };

    printf("\"ik_cases\": [\n");
    for (size_t c = 0; c < ik_cases.size(); ++c) {
        Manipulator m = makeStandardArm();
        m.setQ(ik_cases[c].q0);
        bool conv = m.solveIK(ik_cases[c].target, ik_cases[c].opts);
        printf("  {\"target\": ");
        pvec3(ik_cases[c].target);
        printf(", \"q0\": ");
        pqvec(ik_cases[c].q0);
        printf(", \"opts\": ");
        popts(ik_cases[c].opts);
        printf(", \"converged\": %s", conv ? "true" : "false");
        printf(", \"q_final\": ");
        pqvec(m.q());
        printf(", \"tip_final\": ");
        pvec3(m.tipPosition());
        printf("}%s\n", (c + 1 < ik_cases.size()) ? "," : "");
    }
    printf("]\n}\n");
    return 0;
}
